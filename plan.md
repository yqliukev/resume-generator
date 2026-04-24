Refactor what persistence.py was building towards into persistence_v2 built around 3 classes:

1. LinkRecord: linking class between a ResumeDocument source file and a target ResumeDocument file. Has a corresponding metadata json file in the file system.
The class and json file should encapture what sections and entries of the source file are present in each target file. Ensure that target files do not have any data not available in the source file.

2. SourceFile: child of the ResumeDocument class which represents files which are parsed and used to create GeneratedFiles

3. GeneratedFile: child of the ResumeDocument class which represents target files which are assembled from SourceFiles

Add the path of the underlying files of SourceFile and GeneratedFile as a property. Move the classes to models.py

Delete all irrelevant or unused functions, only keep json conversion functions if they are likely to be used within this codebase.

All documents will be either a SourceFile or a GeneratedFile. Turn ResumeDocument into an abstract class. 
