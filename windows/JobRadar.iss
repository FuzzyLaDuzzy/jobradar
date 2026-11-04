; The Windows installer: JobRadar.exe with Python inside (PyInstaller puts it in dist\JobRadar), for
; this user only, so no administrator is needed. Built by .github/workflows/apps.yml:
;   iscc /DVersion=1.2.3 windows\JobRadar.iss
; The data (config.yaml, .env, jobradar.db) stays in %LOCALAPPDATA%\JobRadar (windows/start.py), also
; after uninstalling.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{5B0E3C1A-8F2D-4C47-9A51-3D6E2F7B9C10}
AppName=JobRadar
AppVersion={#Version}
AppPublisher=Flávio Silva
AppPublisherURL=https://github.com/FuzzyLaDuzzy/jobradar
DefaultDirName={localappdata}\Programs\JobRadar
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=JobRadar-{#Version}-windows-setup
SetupIconFile=..\jobradar\static\icon.ico
UninstallDisplayIcon={app}\JobRadar.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "pt"; MessagesFile: "compiler:Languages\Portuguese.isl"

[CustomMessages]
en.StartupTask=Open JobRadar when I sign in to Windows
pt.StartupTask=Abrir o JobRadar ao iniciar sessão no Windows
en.SearchTask=Search for jobs every day at 9:00 and 21:00 (only while the computer is on)
pt.SearchTask=Procurar vagas todos os dias às 9h e às 21h (só com o computador ligado)
en.OpenNow=Open JobRadar
pt.OpenNow=Abrir o JobRadar

[Tasks]
Name: "startup"; Description: "{cm:StartupTask}"
Name: "search"; Description: "{cm:SearchTask}"

[Files]
Source: "..\dist\JobRadar\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\JobRadar"; Filename: "{app}\JobRadar.exe"
Name: "{userstartup}\JobRadar"; Filename: "{app}\JobRadar.exe"; Tasks: startup

[Run]
; JobRadar.exe refresh: a search without the window, which shows a notification when it finds new jobs
Filename: "schtasks.exe"; Parameters: "/Create /F /SC DAILY /ST 09:00 /TN ""JobRadar search 9h"" /TR ""\""{app}\JobRadar.exe\"" refresh"""; Flags: runhidden; Tasks: search
Filename: "schtasks.exe"; Parameters: "/Create /F /SC DAILY /ST 21:00 /TN ""JobRadar search 21h"" /TR ""\""{app}\JobRadar.exe\"" refresh"""; Flags: runhidden; Tasks: search
Filename: "{app}\JobRadar.exe"; Description: "{cm:OpenNow}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""JobRadar search 9h"""; Flags: runhidden; RunOnceId: "DeleteSearch9h"
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""JobRadar search 21h"""; Flags: runhidden; RunOnceId: "DeleteSearch21h"
