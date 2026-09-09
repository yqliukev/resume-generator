# Generated file management - plan

The new feature addition is a management system for generated file.

## Current application status

GUI activated from running [v1.py](../src/v1.py). Parses a master tex file with a format similar to a [template](<../Base Template.tex>). Through the GUI, the user selects items to include, and generates the corresponding file. A [links json file](../Base%20Template.resume-links.json) is generated, which allows the user to update all generated files after the template is changed.

## Goal

- A system for managing different versions of each item. When generating a file, the user can choose which version cleanly

## Criterias
- Consider how the template file can be restructured, but never update it directly. Instruct the user through chat. 
- The UI of showing different versions should be able to be clearly differentiated by the user.
