; Inno Setup script for the Windows installer, dist\SemanticNets-VERSION-setup.exe:
; it installs the PyInstaller build ("dist\Semantic Nets\", made by
; packaging\semanticNets.spec), with a Start menu entry, an uninstaller, and
; .snm and .snv files opening in it. By default it's installed for the user
; alone (no administrator needed); the installer offers all users too.
;
;   iscc /DVersion=1.0 packaging\installer.iss
;
; (Inno Setup: https://jrsoftware.org/isinfo.php; it's on GitHub's Windows
; runners: see .github\workflows\build.yml.)

#ifndef Version
  #define Version "0.0"
#endif

[Setup]
AppId={{6F1C2B9E-7C1A-4E3B-9B7E-5E3A1D2C4B10}
AppName=Semantic Nets
AppVersion={#Version}
AppPublisher=Rob Kremer
AppPublisherURL=https://github.com/robkremer/semanticNets
AppSupportURL=https://robkremer.github.io/semanticNets/
DefaultDirName={autopf}\Semantic Nets
DefaultGroupName=Semantic Nets
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
OutputDir=..\dist
OutputBaseFilename=SemanticNets-{#Version}-setup
SetupIconFile=sn.ico
UninstallDisplayIcon={app}\Semantic Nets.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Semantic Nets\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Semantic Nets"; Filename: "{app}\Semantic Nets.exe"
Name: "{autodesktop}\Semantic Nets"; Filename: "{app}\Semantic Nets.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.snm"; ValueType: string; ValueName: ""; ValueData: "SemanticNets.Model"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.snm\OpenWithProgids"; ValueType: string; ValueName: "SemanticNets.Model"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\SemanticNets.Model"; ValueType: string; ValueName: ""; ValueData: "Semantic Nets Model"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SemanticNets.Model\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Semantic Nets.exe,0"
Root: HKA; Subkey: "Software\Classes\SemanticNets.Model\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Semantic Nets.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.snv"; ValueType: string; ValueName: ""; ValueData: "SemanticNets.View"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.snv\OpenWithProgids"; ValueType: string; ValueName: "SemanticNets.View"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\SemanticNets.View"; ValueType: string; ValueName: ""; ValueData: "Semantic Nets View"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SemanticNets.View\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Semantic Nets.exe,0"
Root: HKA; Subkey: "Software\Classes\SemanticNets.View\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Semantic Nets.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\Semantic Nets.exe\SupportedTypes"; ValueType: string; ValueName: ".snm"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\Semantic Nets.exe\SupportedTypes"; ValueType: string; ValueName: ".snv"; ValueData: ""

[Run]
Filename: "{app}\Semantic Nets.exe"; Description: "{cm:LaunchProgram,Semantic Nets}"; Flags: nowait postinstall skipifsilent
