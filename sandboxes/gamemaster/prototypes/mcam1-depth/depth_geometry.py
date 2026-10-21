"""Calibrated, metric multi-view geometry and the known upright Atom box."""
import math
import cv2
import numpy as np
from depth_config import ATOM


def rz(degrees):
    a = math.radians(degrees)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1.]])


def camera_pose(pose, config):
    """Return camera-to-world rotation and optical centre in robot base mm."""
    roll, pitch, yaw = np.radians(config['mount_rpy_deg'])
    rx = np.array([[1., 0, 0], [0, np.cos(roll), -np.sin(roll)], [0, np.sin(roll), np.cos(roll)]])
    ry = np.array([[np.cos(pitch), 0, np.sin(pitch)], [0, 1., 0], [-np.sin(pitch), 0, np.cos(pitch)]])
    holder = rz(pose[3]) if config['follows_tool_rotation'] else np.eye(3)
    rotation = holder @ rz(math.degrees(yaw)) @ ry @ rx
    centre = np.asarray(pose[:3]) + holder @ np.asarray(config['camera_offset_mm'])
    return rotation, centre


def lens_model(config, width, height):
    lens = config['intrinsics']
    if lens:
        if (width, height) != (lens['width'], lens['height']):
            raise ValueError('Video mode changed: calibrate this resolution or clear the lens calibration')
        return np.array(lens['matrix']), np.array(lens['distortion']), 'calibrated'
    focal = width/(2*math.tan(math.radians(config['horizontal_fov_deg']/2)))
    return np.array([[focal, 0, width/2], [0, focal, height/2], [0, 0, 1.]]), np.zeros(5), 'nominal FOV'


def triangulate(first, second, pose_a, pose_b, config, matrix, distortion, *, details=False):
    ra, ca = camera_pose(pose_a, config)
    rb, cb = camera_pose(pose_b, config)
    a = cv2.undistortPoints(np.float64(first).reshape(-1, 1, 2), matrix, distortion).reshape(-1, 2)
    b = cv2.undistortPoints(np.float64(second).reshape(-1, 1, 2), matrix, distortion).reshape(-1, 2)
    pa, pb = np.column_stack((ra.T, -ra.T@ca)), np.column_stack((rb.T, -rb.T@cb))
    homogeneous = cv2.triangulatePoints(pa, pb, a.T, b.T).T
    good_w = np.abs(homogeneous[:, 3]) > 1e-9
    world = homogeneous[:, :3] / np.where(good_w, homogeneous[:, 3], np.nan)[:, None]
    ac, bc = (world-ca)@ra, (world-cb)@rb
    ray_a, ray_b = world-ca, world-cb
    with np.errstate(invalid='ignore', divide='ignore'):
        cosine = np.sum(ray_a*ray_b, axis=1)/(np.linalg.norm(ray_a, axis=1)*np.linalg.norm(ray_b, axis=1))
        angle = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
        residual = np.maximum(np.linalg.norm(ac[:, :2]/ac[:, 2:3]-a, axis=1),
                              np.linalg.norm(bc[:, :2]/bc[:, 2:3]-b, axis=1))*max(matrix[0, 0], matrix[1, 1])
    good = (good_w & np.isfinite(world).all(axis=1) & (ac[:, 2] > 20) & (bc[:, 2] > 20)
            & (ac[:, 2] < 1200) & (bc[:, 2] < 1200) & (angle > .7) & (residual < 1.5))
    result = (world[good], np.asarray(second)[good], bc[good, 2], residual[good])
    if details:
        return (*result, dict(indices=np.flatnonzero(good), anchor_depths=ac[good, 2],
                              rotation=ra.T@rb, centre=ra.T@(cb-ca)))
    return result


def translation_depth(first, second, baseline, matrix, distortion, *, details=False):
    """Infer translation direction from video; measured TCP travel supplies scale.

    Requires a rigid mount and constant tool orientation. No camera-to-arm
    orientation or lens offset is used. Returned coordinates are in the SECOND
    camera, so they must never be used as a robot/world playfield plane.
    """
    empty = (np.empty((0, 3)), np.empty((0, 2)), np.empty(0), np.empty(0))
    if details:
        empty = (*empty, dict(indices=np.empty(0, dtype=int), anchor_depths=np.empty(0),
                             rotation=np.eye(3), centre=np.zeros(3)))
    if not np.isfinite(baseline) or not 5 <= baseline <= 40 or len(first) < 12:
        return empty
    a = cv2.undistortPoints(np.float64(first).reshape(-1, 1, 2), matrix, distortion).reshape(-1, 2)
    b = cv2.undistortPoints(np.float64(second).reshape(-1, 1, 2), matrix, distortion).reshape(-1, 2)
    rays_a, rays_b = np.column_stack((a, np.ones(len(a)))), np.column_stack((b, np.ones(len(b))))
    normals = np.cross(rays_a, rays_b)
    lengths = np.linalg.norm(normals, axis=1)
    moving = np.isfinite(normals).all(axis=1) & (np.linalg.norm(np.asarray(second)-first, axis=1) > 1.5) & (lengths > 1e-8)
    if moving.sum() < 12:
        return empty
    a, b, rays_a, normals = a[moving], b[moving], rays_a[moving], normals[moving]
    indices = np.flatnonzero(moving)
    pixels = np.asarray(second)[moving]
    normals /= lengths[moving, None]
    focal = max(matrix[0, 0], matrix[1, 1])
    def errors(direction):
        lines = np.cross(direction, rays_a)
        return np.abs(np.sum(lines*np.column_stack((b, np.ones(len(b)))), axis=1))/np.maximum(np.linalg.norm(lines[:, :2], axis=1), 1e-9)*focal
    best = np.zeros(len(a), dtype=bool)
    rng = np.random.default_rng(19)
    for _ in range(100):
        pair = normals[rng.choice(len(normals), 2, replace=False)]
        direction = np.cross(*pair)
        if np.linalg.norm(direction) < 1e-5:
            continue
        inliers = errors(direction) < 1.
        if inliers.sum() > best.sum():
            best = inliers
    if best.sum() < max(12, .65*len(a)):
        return empty
    _, singular, vectors = np.linalg.svd(normals[best], full_matrices=False)
    if singular[1]/np.sqrt(best.sum()) < .04 or np.min(np.ptp(pixels[best], axis=0)) < 20:
        return empty
    direction = vectors[-1]
    best &= errors(direction) < 1.
    a, b, pixels = a[best], b[best], pixels[best]
    indices = indices[best]
    results = []
    for sign in (1, -1):
        centre = direction*baseline*sign
        homogeneous = cv2.triangulatePoints(np.column_stack((np.eye(3), np.zeros(3))),
                                            np.column_stack((np.eye(3), -centre)), a.T, b.T).T
        with np.errstate(invalid='ignore', divide='ignore'):
            world = homogeneous[:, :3]/homogeneous[:, 3:]
            current = world-centre
            angle = np.degrees(np.arccos(np.clip(np.sum(world*current, axis=1)/(np.linalg.norm(world, axis=1)*np.linalg.norm(current, axis=1)), -1, 1)))
            residual = np.maximum(np.linalg.norm(world[:, :2]/world[:, 2:]-a, axis=1),
                                  np.linalg.norm(current[:, :2]/current[:, 2:]-b, axis=1))*focal
        good = (np.isfinite(current).all(axis=1) & (world[:, 2] > 20) & (current[:, 2] > 20)
                & (world[:, 2] < 1200) & (current[:, 2] < 1200) & (angle > .7) & (residual < 1.5))
        result = (current[good], pixels[good], current[good, 2], residual[good])
        if details:
            result = (*result, dict(indices=indices[good], anchor_depths=world[good, 2],
                                    rotation=np.eye(3), centre=centre))
        results.append(result)
    return max(results, key=lambda result: len(result[0]))


def fit_surface(points):
    if len(points) < 12:
        raise ValueError('Need at least 12 reliable surface points; use sideways motion and textured markings')
    best = np.zeros(len(points), dtype=bool)
    rng = np.random.default_rng(7)
    for _ in range(100):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        normal = np.cross(b-a, c-a)
        length = np.linalg.norm(normal)
        if length < 1e-6:
            continue
        normal /= length
        if abs(normal[2]) < math.cos(math.radians(20)):
            continue
        inliers = np.abs((points-a)@normal) < 1.5
        if inliers.sum() > best.sum():
            best = inliers
    if best.sum() < max(12, .65*len(points)):
        raise ValueError('No consistent horizontal surface; check mounting, ROI and animated content')
    selected = points[best]
    centre = selected.mean(axis=0)
    _, singular, vectors = np.linalg.svd(selected-centre, full_matrices=False)
    if singular[1]/math.sqrt(len(selected)) < 3:
        raise ValueError('Surface points are too tightly clustered for a plane')
    normal = vectors[-1]
    if normal[2] < 0:
        normal = -normal
    if normal[2] < math.cos(math.radians(20)):
        raise ValueError('Surface orientation does not match a horizontal playfield')
    offset = -float(normal@centre)
    rms = float(np.sqrt(np.mean((selected@normal+offset)**2)))
    return dict(normal=normal.tolist(), offset=offset, rms_mm=rms, inliers=int(best.sum())), best


def clearance(pose, plane, config):
    """Lowest corner; upright Atom, centred under its suction contact."""
    rotation = rz(pose[3])
    contact = np.asarray(pose[:3]) + rotation@np.asarray(config['contact_offset_mm'])
    half_x, half_y = ATOM['width_mm']/2, ATOM['length_mm']/2
    corners = np.array([[x, y, -ATOM['height_mm']] for x in (-half_x, half_x) for y in (-half_y, half_y)])
    world = corners@rotation.T+contact
    return float(np.min(world@np.asarray(plane['normal'])+plane['offset']))
