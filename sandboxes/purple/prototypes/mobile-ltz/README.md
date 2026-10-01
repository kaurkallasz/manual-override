Purple Mobile LTZ shares all frontend features with Green through
`shared/mobile_ltz`; its own module supplies Purple identity and discovers the
local Purple LTX controller. See the common behavior specification at
`sandboxes/green/prototypes/mobile-ltz/SPECIFICATION.md`.

Purple starts with the 180° view enabled. Toggle the header button to return to
the camera orientation. The video, reach boundaries and targeting rotate
together; all commands retain the original calibrated coordinates and Purple's
robot safety checks. Connecting Purple still requires its robot network link,
fresh feedback, and its own saved calibration.
