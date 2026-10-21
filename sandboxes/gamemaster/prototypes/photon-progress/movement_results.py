"""Validate bounded optional movement evidence on settlement and backup import."""
import math


def validate_movement(value):
    if value is None:
        return
    def number(v, low, high):
        if type(v) not in (int,float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError('Invalid robot movement coordinate or time')
        return v
    if (not isinstance(value,dict) or type(value.get('version')) is not int or value['version'] != 1
            or value.get('units') != 'mm' or value.get('height_basis') != 'Calibrated ground plane'):
        raise ValueError('Invalid robot movement format')
    duration = number(value.get('duration_s'),0,86400*30)
    field = value.get('field')
    if field is not None:
        if not isinstance(field,dict):raise ValueError('Invalid movement field')
        number(field.get('width_mm'),100,5000);number(field.get('height_mm'),100,5000)
        if not isinstance(field.get('core'),list) or len(field['core']) != 2:raise ValueError('Invalid movement center')
        for v in field['core']:number(v,0,1)
    arms = value.get('arms')
    if not isinstance(arms,dict) or set(arms) != {'green','purple'}:raise ValueError('Invalid movement sides')
    for arm in arms.values():
        if not isinstance(arm,dict) or arm.get('status') not in ('ready','partial','unavailable'):raise ValueError('Invalid movement status')
        if arm.get('error') is not None and (not isinstance(arm['error'],str) or len(arm['error'])>240):raise ValueError('Invalid movement error')
        if type(arm.get('gaps')) is not int or not 0 <= arm['gaps'] <= 100000000:raise ValueError('Invalid movement gaps')
        if any(type(arm.get(k)) is not bool for k in ('simplified','truncated')):raise ValueError('Invalid movement flags')
        segments = arm.get('segments')
        if not isinstance(segments,list) or len(segments)>128:raise ValueError('Too many movement segments')
        total = 0;last = -1
        for segment in segments:
            if field is None or not isinstance(segment,list) or not segment:raise ValueError('Invalid movement segment')
            total += len(segment)
            if total>3000:raise ValueError('Too many movement points')
            for point in segment:
                if not isinstance(point,list) or len(point)!=4:raise ValueError('Invalid movement point')
                last = number(point[0],last,duration)
                number(point[1],-10000,15000);number(point[2],-10000,15000);number(point[3],-500,2000)
        if bool(segments) == (arm['status']=='unavailable'):raise ValueError('Movement availability disagrees with points')
