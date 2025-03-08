# VDBX.io ESPHome Configs

A modular set of YAML files to use in ESPHome with hardware from VDBX.io

## Breaking changes
25.03 - Removed number.hours_counter from base config due to calculation bug. Replaced with uptime sensor in decimal hours. Working on an updated "engine hours" counter with more features. 

## Example usage

change `flip-c3.yaml` to any in the root directory

```yaml
packages:
  vdbxio.FLIP-C3: github://vdbxio/esphome-configs/flip-c3.yaml
```

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

24.09 - This is now ahead of the wiki source with some minor cleanup, target changes, and slight improvements.

24.08 -This _will be_ the new repository for configs which were previously in our wiki repo.

## TODO:

*   Github Task to build firmware and manifest
*   Add new remote update feature
*   add 
*   clean up a bit more
*   properly add CC-BY-SA 4.0 License