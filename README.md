# VDBX.io ESPHome Configs

A modular set of YAML files to use in ESPHome with hardware from VDBX.io

## Example usage

change `xxx.yaml` to any in the root directory

```yaml
packages:
  flip-c3: github://vdbxio/esphome-configs/xxx.yaml
```
`*.factory.yaml` files are for building factory firmware
`*.import.yaml` files are copied directly to a fresh yaml when importing into ESPHome
`flip-c3.yaml` is legacy for FLIP_C3 devices prior to 1.3.0 since they still point here for simple dash import.



## Folder Layout

*   \*.yaml - Device Configs
*   /blueprints - HA Blueprints for use with devices
*   /other - stuff I'm working on and prototypes to be chopped up
*   /packages - baseline configs and combiners
    *   /include - functions
    *   /parts - component setups
    *   TODO - simplify baseline files - maybe /base
*   /bin - binary packages and manifest for web installer
*   upload.py - a script to batch upload firmware to devices
*   usbmon.py - a script to help track down bad cables by monitoring connection stability

## Changelog
26.06 - Finalize PwrTool config and update FLIP_C3 with custom full imports into esphome dashboard

25.07 - Working on an overhaul to all linked files and removing unnessary components when adopting into ESPHome - Staring work on Github automatic builds on release.

25.03 - Removed number.hours_counter from base config due to calculation bug. Replaced with uptime sensor in decimal hours. Working on an updated "engine hours" counter with more features. 

24.09 - This is now ahead of the wiki source with some minor cleanup, target changes, and slight improvements.

24.08 -This _will be_ the new repository for configs which were previously in our wiki repo.

## TODO:

*   Github Task to build firmware and manifest (in-progress)
*   Add new remote update feature
*   add 
*   clean up a bit more
*   properly add CC-BY-SA 4.0 License