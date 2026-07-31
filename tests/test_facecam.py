import numpy as np

from clipengine.edit.facecam import find_facecam


def _synthetic_frames(
    n=16, h=270, w=480, cam=(40, 30, 160, 120), noise_seed=0, with_cam=True
):
    """Moving-noise 'gameplay' with an optional static bright-bordered facecam."""
    rng = np.random.default_rng(noise_seed)
    frames = rng.uniform(0, 255, size=(n, h, w)).astype(np.float32)
    if with_cam:
        x, y, cw, ch = cam
        for f in frames:
            # facecam interior: its own moving noise (a face moves too)
            f[y : y + ch, x : x + cw] = rng.uniform(60, 120, size=(ch, cw))
            # static bright border, 2px, constant across frames
            f[y : y + 2, x : x + cw] = 255
            f[y + ch - 2 : y + ch, x : x + cw] = 255
            f[y : y + ch, x : x + 2] = 255
            f[y : y + ch, x + cw - 2 : x + cw] = 255
    return frames


def test_detects_static_bordered_rectangle():
    cam = (40, 30, 160, 120)
    found = find_facecam(_synthetic_frames(cam=cam))
    assert found is not None
    r = found.region
    # allow a few px slack: gradient edges sit next to the border pixels
    assert abs(r.x - cam[0]) <= 4 and abs(r.y - cam[1]) <= 4
    assert abs(r.w - cam[2]) <= 8 and abs(r.h - cam[3]) <= 8
    assert found.score > 0.5


def test_no_facecam_returns_none():
    found = find_facecam(_synthetic_frames(with_cam=False))
    assert found is None


def test_corner_facecam():
    cam = (0, 0, 140, 100)
    found = find_facecam(_synthetic_frames(cam=cam))
    # border at frame edge loses two perimeter sides to the frame boundary;
    # detection may shift slightly but must stay inside the true region's vicinity
    assert found is not None
    assert found.region.x <= 8 and found.region.y <= 8


def test_rejects_wrong_aspect():
    # a very wide thin banner (e.g. a ticker) must not be detected as a facecam
    frames = _synthetic_frames(with_cam=False)
    for f in frames:
        f[240:260, 0:480] = 255  # 480x20 banner: aspect 24, way out of range
    found = find_facecam(frames)
    if found is not None:
        r = found.region
        assert not (r.h <= 30 and r.w >= 400), "banner misdetected as facecam"
