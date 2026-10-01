"""Complete, asymmetric measurements for isolated tests; never real hardware."""
import copy


def calibrated(owner, revision=3):
    cal=owner._default_calibration2();cal['revision']=revision
    cal['shared_z']['transport_height']=60
    coords={30:(.5,.2),31:(.2,.2),32:(.5,.8),33:(.8,.8),34:(.2,.8),35:(.8,.2)}
    for side,arm in cal['arms'].items():
        arm.update(pickup_height=10,updated_at=1000,camera_revision='fixture',camera_view='rot180' if side=='purple' else 'normal')
        for p in arm['points'].values():
            u,v=coords[p['marker']]
            if side=='purple':u,v=1-u,1-v
            p.update(camera=dict(u=u,v=v),pose=dict(set=True,x=260+100*u,y=-80+160*v,z=10,r=0))
        for marker in (31,35,33,34):
            p=next(p for p in arm['points'].values() if p['marker']==marker)
            arm['parallax_points'][str(marker)]={'marker':marker,'height_mm':30,'ground':copy.deepcopy(p['camera']),
                                               'raised':dict(u=p['camera']['u']+.015,v=p['camera']['v']-.02)}
    return cal


def seed(owner):
    old=calibrated(owner,2)
    for side,arm in old['arms'].items():
        arm['updated_at']=500
        for p in arm['points'].values():p['camera']['u']-=.025
        owner._lessons.archive_rig(side,old)
    owner._calibration2=calibrated(owner)
    owner._save_calibration2()
