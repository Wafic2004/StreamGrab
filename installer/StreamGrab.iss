; StreamGrab installer (Inno Setup 6)
; Build:  installer\build_installer.bat   ->  installer\Output\StreamGrab_Setup_<version>.exe
;
; Everything the app needs ships inside dist\StreamGrab (built by build.bat):
;   - Python runtime, Qt (PySide6) and the Visual C++ runtime DLLs
;   - yt-dlp download engine (built in)
;   - bin\ffmpeg.exe, bin\ffprobe.exe  (merging / converting)
;   - bin\deno.exe                     (solves YouTube's JavaScript challenges)
; so nothing else has to be downloaded or installed on the user's PC.

#define AppName      "StreamGrab"
#ifndef AppVersion
  #define AppVersion "1.0.1"
#endif
#define AppPublisher "StreamGrab"
#define AppExe       "StreamGrab.exe"
#define SrcDir       "..\dist\StreamGrab"

[Setup]
AppId={{6C2E7A54-3B1F-4E8D-9A61-5F0B2C7D4E91}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments=Download YouTube videos and audio in any quality. Free, no ads, no account.
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}

; Per-user install by default: no administrator prompt. Users may choose "all users" in the first step.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; Looks
WizardStyle=modern
DisableWelcomePage=no
WizardSizePercent=100
SetupIconFile=..\assets\streamgrab.ico
WizardImageFile=wizard_100.bmp,wizard_200.bmp
WizardSmallImageFile=wizard_small_100.bmp,wizard_small_200.bmp
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}

; Close a running StreamGrab before updating it
CloseApplications=force
RestartApplications=no

; Output
OutputDir=Output
OutputBaseFilename={#AppName}_Setup_{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=2
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nStreamGrab downloads YouTube videos, playlists and audio in the quality you choose. Everything it needs is included - nothing else to install.
FinishedLabel=StreamGrab is installed.%n%nOpen it from the Start menu or the desktop. Paste a YouTube link and press Download - files are saved to Downloads\StreamGrab unless you pick another folder.

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[InstallDelete]
; Remove the previous version's program files so no outdated library is left behind on upgrade
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\bin"

[Files]
Source: "{#SrcDir}\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SrcDir}\bin\ffmpeg.exe";  DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#SrcDir}\bin\ffprobe.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#SrcDir}\bin\deno.exe";    DestDir: "{app}\bin"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Download YouTube videos and audio"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Download YouTube videos and audio"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open StreamGrab now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Files the app writes next to itself at run time (none expected, but keep the folder clean)
Type: dirifempty; Name: "{app}"

[Code]
{ ---- running-app detection (WMI), used by the uninstaller ---- }
function AppProcesses(): Variant;
var
  Locator, Service: Variant;
begin
  Locator := CreateOleObject('WbemScripting.SWbemLocator');
  Service := Locator.ConnectServer('.', 'root\CIMV2');
  Result := Service.ExecQuery('SELECT ProcessId, ExecutablePath FROM Win32_Process WHERE Name = ''{#AppExe}''');
end;

function ProcPath(P: Variant): String;
var
  S: String;
begin
  Result := '';
  try
    if not VarIsNull(P.ExecutablePath) then
    begin
      S := P.ExecutablePath;
      Result := Lowercase(S);
    end;
  except
    Result := '';
  end;
end;

function IsAppRunning(): Boolean;
var
  Procs, P: Variant;
  I: Integer;
  AppDir: String;
begin
  Result := False;
  AppDir := Lowercase(ExpandConstant('{app}'));
  try
    Procs := AppProcesses();
    for I := 0 to Procs.Count - 1 do
    begin
      P := Procs.ItemIndex(I);
      if Pos(AppDir, ProcPath(P)) = 1 then
        Result := True;
    end;
  except
    Result := False;
  end;
end;

procedure CloseApp();
var
  Procs, P: Variant;
  I: Integer;
  AppDir: String;
begin
  AppDir := Lowercase(ExpandConstant('{app}'));
  try
    Procs := AppProcesses();
    for I := 0 to Procs.Count - 1 do
    begin
      P := Procs.ItemIndex(I);
      if Pos(AppDir, ProcPath(P)) = 1 then
        P.Terminate();
    end;
  except
  end;
  { give Windows a moment to release the files (and FFmpeg, if a download was running) }
  for I := 1 to 20 do
  begin
    if not IsAppRunning() then
      Break;
    Sleep(250);
  end;
  Sleep(500);
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  while IsAppRunning() do
  begin
    if UninstallSilent() then
    begin
      CloseApp();
      Break;
    end;
    if MsgBox('StreamGrab is open. It has to close before it can be uninstalled.' + #13#10 + #13#10 +
              'Close StreamGrab now and continue?' + #13#10 +
              '(A download in progress will be stopped.)',
              mbConfirmation, MB_OKCANCEL) = IDOK then
      CloseApp()
    else
    begin
      Result := False;
      Exit;
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWin64 then
  begin
    MsgBox('StreamGrab needs 64-bit Windows 10 or later.', mbCriticalError, MB_OK);
    Result := False;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\StreamGrab');
    { Downloaded videos are never touched. Only the app's own settings and engine updates are offered for removal. }
    if (DirExists(DataDir) or RegKeyExists(HKCU, 'Software\StreamGrab')) and not UninstallSilent then
    begin
      if MsgBox('Also remove your StreamGrab settings and downloaded engine updates?' + #13#10 + #13#10 +
                'Your downloaded videos and music are NOT deleted.' + #13#10 +
                'Choose No to keep your settings for a future install.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
        RegDeleteKeyIncludingSubkeys(HKCU, 'Software\StreamGrab');
      end;
    end;
  end;
end;
