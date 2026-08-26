#define AppName "Entok Vision Lite"
#define AppVersion "0.1.0"
#ifndef Variant
  #define Variant "CPU"
#endif
#ifndef SourceDir
  #error SourceDir must be provided by the build script
#endif
#ifndef OutputDir
  #error OutputDir must be provided by the build script
#endif
#ifndef IconFile
  #error IconFile must be provided by the build script
#endif

[Setup]
AppId={{9AC44008-4F47-46EC-BA2B-1F8B7D41D837}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion} ({#Variant})
AppPublisher=Marshel2727
DefaultDirName={localappdata}\Programs\Entok Vision Lite
DefaultGroupName=Entok Vision Lite
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=EntokVisionLite-{#AppVersion}-Windows-x64-{#Variant}-Setup
#if Variant == "GPU-CUDA124"
DiskSpanning=yes
DiskSliceSize=1900000000
SlicesPerDisk=1
#endif
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\EntokVisionLite.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=0.1.0.0
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "indonesian"; MessagesFile: "{#SourcePath}\languages\Indonesian.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Entok Vision Lite"; Filename: "{app}\EntokVisionLite.exe"
Name: "{autodesktop}\Entok Vision Lite"; Filename: "{app}\EntokVisionLite.exe"; Tasks: desktopicon
Name: "{autoprograms}\Pengaturan Entok Vision Lite"; Filename: "{app}\EntokVisionLite.exe"; Parameters: "--settings"

[Tasks]
Name: "desktopicon"; Description: "Buat shortcut di Desktop"; GroupDescription: "Shortcut tambahan:"; Flags: unchecked

[Run]
Filename: "{app}\EntokVisionLite.exe"; Description: "Jalankan Entok Vision Lite"; Flags: nowait postinstall skipifsilent
