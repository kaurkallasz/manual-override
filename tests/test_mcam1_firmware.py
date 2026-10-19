"""Firmware bundle, HTTP boundary and no-write preflight tests; no real USB I/O."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile
from flask import Flask
from test_photon_framework import load

module = load('mcam1')
import mcam1_firmware as fw
import importlib.util
spec = importlib.util.spec_from_file_location('mcam1_flash_worker', module.HERE / 'flash_worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'bundle.zip'
        self.builtin = module.HERE / 'firmware/xiao-ai-v1-bulk.zip'
        with zipfile.ZipFile(self.builtin) as z:
            self.files = {name:z.read(name) for name in z.namelist()}
        self.manifest = json.loads(self.files['manifest.json'])
        self.manager = fw.FirmwareManager(module.HERE)
        self.target = dict(token='token', port='/dev/cu.test', serial='1C:DB:D4:43:34:4C', flashable=True)

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def bundle(self):
        self.files['manifest.json'] = json.dumps(self.manifest).encode()
        with zipfile.ZipFile(self.path,'w',zipfile.ZIP_DEFLATED) as z:
            for name, raw in self.files.items(): z.writestr(name, raw)
        return self.path

    def test_bundled_release_is_current_complete_ai_build(self):
        info, images = fw.validate_bundle(self.builtin)
        self.assertEqual(info['revision'],'ai-v1')
        self.assertEqual(info['application_sha256'],'28274e6ad6c422727055f0f4f287fca45b53e6a1e22aaf88b91bed187adfff42')
        self.assertEqual(set(images),set(fw.LAYOUT.values()))
        self.assertEqual(info['ai']['classes'],['person'])

    def test_tampered_image_rejected(self):
        self.files['firmware.bin'] += b'tampered'
        with self.assertRaisesRegex(ValueError,'SHA-256'): fw.validate_bundle(self.bundle())

    def test_wrong_chip_rejected_even_with_updated_hash(self):
        raw=bytearray(self.files['firmware.bin']);raw[12]=0
        self.files['firmware.bin']=bytes(raw)
        self.manifest['sha256']['firmware.bin']=hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'ESP32-S3'): fw.validate_bundle(self.bundle())

    def test_corrupt_image_digest_rejected_even_with_updated_manifest_hash(self):
        raw=bytearray(self.files['firmware.bin']);raw[1000]^=1
        self.files['firmware.bin']=bytes(raw)
        self.manifest['sha256']['firmware.bin']=hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'checksum'): fw.validate_bundle(self.bundle())

    def test_arbitrary_flash_layout_rejected(self):
        self.manifest['flash_layout']['0x9000']='erase-nvs.bin'
        with self.assertRaisesRegex(ValueError,'offsets'): fw.validate_bundle(self.bundle())

    def test_old_partition_layout_rejected_even_with_valid_md5(self):
        raw=bytearray(self.files['partitions.bin']);raw[44:48]=(0x200000).to_bytes(4,'little')
        raw[80:96]=hashlib.md5(raw[:64]).digest()
        self.files['partitions.bin']=bytes(raw)
        self.manifest['sha256']['partitions.bin']=hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'4 MiB'): fw.validate_bundle(self.bundle())

    def test_path_traversal_and_duplicate_entries_rejected(self):
        self.files['../outside']=b'no'
        with self.assertRaisesRegex(ValueError,'Unsafe'): fw.validate_bundle(self.bundle())
        del self.files['../outside']
        self.bundle()
        with zipfile.ZipFile(self.path,'a') as z:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore');z.writestr('manifest.json','{}')
        with self.assertRaisesRegex(ValueError,'duplicate'): fw.validate_bundle(self.path)

    def test_invalid_upload_does_not_replace_previously_valid_bundle(self):
        info=self.manager.stage(io.BytesIO(self.builtin.read_bytes()))
        with self.assertRaises(ValueError): self.manager.stage(io.BytesIO(b'raw model'))
        self.assertEqual(info['id'],self.manager.snapshot()['upload']['id'])
        fw.validate_bundle(Path(self.manager.temp.name)/'upload.zip')

    def test_stale_target_or_missing_confirmation_never_releases_camera(self):
        release=mock.Mock()
        with mock.patch.object(fw,'resolve_device',side_effect=ValueError('USB identity changed')):
            with self.assertRaises(ValueError): self.manager.start('builtin','old','XIAO old',release)
        with mock.patch.object(fw,'resolve_device',return_value=self.target):
            with self.assertRaisesRegex(ValueError,'Confirm'): self.manager.start('builtin','token','wrong',release)
        release.assert_not_called()
        self.assertEqual(self.manager.snapshot()['job']['status'],'idle')

    def test_running_job_blocks_second_flash_and_upload(self):
        self.manager.job['status']='running'
        with self.assertRaises(RuntimeError): self.manager.start('builtin','token','wrong',mock.Mock())
        with self.assertRaises(RuntimeError): self.manager.stage(io.BytesIO(self.builtin.read_bytes()))

    def test_worker_refuses_wrong_chip_flash_size_identity_and_secure_boot_before_write(self):
        for bad in ['chip','flash','mac','secure']:
            with self.subTest(bad=bad):
                esp=mock.Mock(CHIP_NAME='ESP32-S3',secure_download_mode=False)
                esp.read_mac.return_value=bytes.fromhex('1CDBD443344C')
                esp.get_secure_boot_enabled.return_value=bad=='secure'
                esp.get_flash_encryption_enabled.return_value=False
                esp.run_stub.return_value=esp
                if bad=='chip': esp.CHIP_NAME='ESP32'
                if bad=='mac': esp.read_mac.return_value=bytes.fromhex('001122334455')
                with mock.patch('sys.stdout',new=io.StringIO()), mock.patch.object(worker,'resolve_device',return_value=self.target), mock.patch('esptool.cmds.detect_chip',return_value=esp), mock.patch('esptool.cmds.attach_flash'), mock.patch('esptool.cmds.detect_flash_size',return_value='4MB' if bad=='flash' else '8MB'), mock.patch('esptool.cmds.write_flash') as write:
                    with self.assertRaises(RuntimeError): worker.flash(self.builtin,'token')
                    write.assert_not_called()
                    esp._port.close.assert_called_once()

    def test_worker_writes_and_verifies_same_three_images_before_reset(self):
        esp=mock.Mock(CHIP_NAME='ESP32-S3',secure_download_mode=False)
        esp.read_mac.return_value=bytes.fromhex('1CDBD443344C')
        esp.get_secure_boot_enabled.return_value=esp.get_flash_encryption_enabled.return_value=False
        esp.run_stub.return_value=esp
        order=mock.Mock()
        with mock.patch('sys.stdout',new=io.StringIO()), mock.patch.object(worker,'resolve_device',return_value=self.target), mock.patch('esptool.cmds.detect_chip',return_value=esp) as detect, mock.patch('esptool.cmds.attach_flash'), mock.patch('esptool.cmds.detect_flash_size',return_value='8MB'), mock.patch('esptool.cmds.write_flash') as write, mock.patch('esptool.cmds.verify_flash') as verify:
            order.attach_mock(write,'write');order.attach_mock(verify,'verify');order.attach_mock(esp.hard_reset,'reset')
            worker.flash(self.builtin,'token')
            self.assertEqual(detect.call_args.kwargs['connect_mode'],'no-reset')
            self.assertEqual([call[0] for call in order.mock_calls],['write','verify','reset'])
            self.assertEqual(write.call_args.args,verify.call_args.args)
            self.assertEqual([p[0] for p in write.call_args.args[1]],[0,0x8000,0x10000])
            self.assertFalse(write.call_args.kwargs['force'])
            self.assertFalse(write.call_args.kwargs['erase_all'])

    def test_verification_failure_never_resets_or_reports_verified(self):
        esp=mock.Mock(CHIP_NAME='ESP32-S3',secure_download_mode=False)
        esp.read_mac.return_value=bytes.fromhex('1CDBD443344C')
        esp.get_secure_boot_enabled.return_value=esp.get_flash_encryption_enabled.return_value=False
        esp.run_stub.return_value=esp
        with mock.patch('sys.stdout',new=io.StringIO()) as output, mock.patch.object(worker,'resolve_device',return_value=self.target), mock.patch('esptool.cmds.detect_chip',return_value=esp), mock.patch('esptool.cmds.attach_flash'), mock.patch('esptool.cmds.detect_flash_size',return_value='8MB'), mock.patch('esptool.cmds.write_flash'), mock.patch('esptool.cmds.verify_flash',side_effect=RuntimeError('mismatch')):
            with self.assertRaisesRegex(RuntimeError,'mismatch'):worker.flash(self.builtin,'token')
            self.assertNotIn('MCAM1_PHASE verified',output.getvalue())
            esp.hard_reset.assert_not_called()
            esp._port.close.assert_called_once()

    def test_job_requires_successful_exit_and_verified_phase(self):
        for code, phase, expected in [(0,'verified','done'),(1,'verified','error'),(0,'writing','error')]:
            with self.subTest(code=code,phase=phase):
                process=mock.Mock()
                process.stdout=io.StringIO('MCAM1_PHASE '+phase+'\n')
                process.wait.return_value=code;process.poll.return_value=code
                self.manager.job=dict(status='running',phase='connecting',log=[])
                with mock.patch.object(fw.subprocess,'Popen',return_value=process):
                    self.manager._run(self.builtin,self.target)
                self.assertEqual(self.manager.snapshot()['job']['status'],expected)
                self.assertIsNone(self.manager.process)

    def test_http_upload_boundary_and_flash_lockout(self):
        m=load('mcam1');m._flasher=self.manager;m._capture=mock.Mock();m._controls=mock.Mock()
        app=Flask(__name__);app.register_blueprint(m.bp,name='gamemaster_mcam1');client=app.test_client()
        for endpoint in ['upload','flash']:
            self.assertEqual(client.post('/api/firmware/'+endpoint,headers={'Origin':'https://outside.test'}).status_code,403)
        self.assertEqual(client.post('/api/firmware/flash',json={'port':'/dev/arbitrary'}).status_code,400)
        response=client.post('/api/firmware/upload',data={'bundle':(io.BytesIO(self.builtin.read_bytes()),'firmware.zip')})
        self.assertEqual(response.status_code,200,response.json)
        response.request.environ['wsgi.input'].close()
        response.close();response.request.close()
        self.assertEqual(client.post('/api/controls',data=b'x'*5000).status_code,413)
        self.manager.job['status']='running'
        for endpoint,payload in [('capture',{'action':'start'}),('controls',{'action':'get'}),('ai',{'action':'get'})]:
            self.assertEqual(client.post('/api/'+endpoint,json=payload).status_code,409)
        m._capture.start.assert_not_called();m._controls.request.assert_not_called()


if __name__ == '__main__': unittest.main()
