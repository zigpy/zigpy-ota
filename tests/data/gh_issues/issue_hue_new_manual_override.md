### OTA file

_No response_

### OTA image URL

https://otau.meethue.com/storage/ZGB_100B_010C/0f7ed133-fa2f-48f6-810d-533fd1d4994a/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee

### Manufacturer name

Hue

### Provided URL is an official source from the manufacturer

- [x] The OTA image URL provided is from an official source (e.g., manufacturer's website, official repository)

### How to handle existing images of the same type

Keep all with version constraint (multi-step)

### Release notes

- Bug fixes
- Performance improvements
- Manual override test

### Optional metadata

model_names: [test test, test2]
manufacturer_names: SignifyX
min_current_file_version: 0x01002602
invalid_xx: test

### Checklist

- [x] The OTA image provided is in a supported format (e.g., .zigbee, .ota)
- [ ] I have filled out the release notes to the best of my ability
- [ ] I have the rights to distribute this OTA image
- [ ] The OTA images are tested and verified to work on a physical device

### Additional information

Testing manual override of min_current_file_version. User wants to set it to the newest version (higher than new version) instead of the auto-calculated old version.
