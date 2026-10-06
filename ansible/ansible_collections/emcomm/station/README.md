# emcomm.station

Roles that turn a Debian 13 or Fedora machine into an emcommOS station:
`base` (repository, time sync, radio groups), `toolsets` (emcomm metapackages),
`radio_hw` (station kits and udev rules) and `services` (systemd user units for
rigctld, Direwolf and Pat). Run it with `emcomm bootstrap` or `playbooks/station.yml`.
