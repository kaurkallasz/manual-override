// MCAM1's macOS capture worker. Only the named XIAO UVC device is eligible.
import AVFoundation
import CoreImage
import Foundation
import Darwin

func fail(_ text: String) -> Never {
    FileHandle.standardError.write(Data((text + "\n").utf8))
    exit(2)
}
let args = CommandLine.arguments
guard args.count == 4, let width = Int32(args[1]), let height = Int32(args[2]), let fps = Int32(args[3]),
      [(480,320,30),(320,240,30),(640,480,15)].contains(where: {$0 == (Int(width),Int(height),Int(fps))}) else { fail("Unsupported MCAM1 capture mode") }
let devices = AVCaptureDevice.DiscoverySession(deviceTypes: [.external], mediaType: .video, position: .unspecified).devices
let matches = devices.filter { $0.localizedName == "XIAO USB Webcam LL Bulk" && $0.modelID.contains("VendorID_12346 ProductID_32768") }
guard matches.count == 1 else { fail("Expected one XIAO USB Webcam LL Bulk; reconnect its USB cable.") }
let camera = matches[0]
let permission = DispatchSemaphore(value: 0)
var granted = AVCaptureDevice.authorizationStatus(for: .video) == .authorized
if AVCaptureDevice.authorizationStatus(for: .video) == .notDetermined {
    AVCaptureDevice.requestAccess(for: .video) { result in granted = result; permission.signal() }
    _ = permission.wait(timeout: .now() + 30)
}
guard granted else { fail("Allow camera access for the hub's Python/Terminal in macOS Privacy & Security → Camera.") }
guard let format = camera.formats.first(where: {
    let d = CMVideoFormatDescriptionGetDimensions($0.formatDescription)
    return d.width == width && d.height == height && $0.videoSupportedFrameRateRanges.contains { $0.maxFrameRate >= Double(fps) }
}) else { fail("XIAO does not advertise the requested capture mode.") }
final class Receiver: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let width: Int32
    let height: Int32
    init(width: Int32, height: Int32) { self.width = width; self.height = height }
    let context = CIContext(options: [.cacheIntermediates: false])
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        autoreleasepool {
            guard let pixels = CMSampleBufferGetImageBuffer(sampleBuffer),
                  CVPixelBufferGetWidth(pixels) == Int(width), CVPixelBufferGetHeight(pixels) == Int(height),
                  let jpeg = context.jpegRepresentation(of: CIImage(cvPixelBuffer: pixels), colorSpace: colorSpace,
                      options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: 0.85]) else { return }
            var length = UInt32(jpeg.count).bigEndian
            var packet = Data(bytes: &length, count: 4)
            packet.append(jpeg)
            do { try FileHandle.standardOutput.write(contentsOf: packet) }
            catch { exit(0) } // Parent closed the pipe.
        }
    }
}
do {
    let session = AVCaptureSession()
    let output = AVCaptureVideoDataOutput()
    let receiver = Receiver(width: width, height: height)
    let queue = DispatchQueue(label: "mcam1.capture", qos: .userInitiated)
    let input = try AVCaptureDeviceInput(device: camera)
    session.beginConfiguration()
    session.sessionPreset = .high
    guard session.canAddInput(input), session.canAddOutput(output) else { fail("XIAO capture is unavailable. Close its preview in other apps.") }
    session.addInput(input); session.addOutput(output)
    output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
    output.alwaysDiscardsLateVideoFrames = true
    output.setSampleBufferDelegate(receiver, queue: queue)
    try camera.lockForConfiguration()
    camera.activeFormat = format
    camera.activeVideoMinFrameDuration = format.videoSupportedFrameRateRanges[0].minFrameDuration
    camera.activeVideoMaxFrameDuration = format.videoSupportedFrameRateRanges[0].maxFrameDuration
    camera.unlockForConfiguration()
    session.commitConfiguration()
    session.startRunning()
    try camera.lockForConfiguration()
    camera.activeFormat = format
    camera.activeVideoMinFrameDuration = format.videoSupportedFrameRateRanges[0].minFrameDuration
    camera.activeVideoMaxFrameDuration = format.videoSupportedFrameRateRanges[0].maxFrameDuration
    camera.unlockForConfiguration()
    RunLoop.main.run()
} catch { fail(error.localizedDescription) }
