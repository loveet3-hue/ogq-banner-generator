-- OGQ 배너 생성기 런처 (더블클릭 앱)
-- 이 앱이 있는 폴더의 banner_gen.py 를 터미널에서 실행합니다.

on run
	set appPath to POSIX path of (path to me)
	-- 앱이 있는 폴더 (…/ogq-banner-generator/)
	set AppleScript's text item delimiters to "/"
	set pathItems to text items of appPath
	if last item of pathItems is "" then set pathItems to items 1 thru -2 of pathItems
	set folderPath to (items 1 thru -2 of pathItems as text) & "/"
	set AppleScript's text item delimiters to ""

	set scriptPath to folderPath & "banner_gen.py"
	set runnerPath to folderPath & "build/run.sh"

	-- 스크립트 존재 확인
	try
		do shell script "test -f " & quoted form of scriptPath
	on error
		display dialog "banner_gen.py 파일을 찾을 수 없습니다." & return & return & "이 앱은 ogq-banner-generator 폴더 안에 있어야 합니다. Drive에서 폴더를 통째로 다운로드해 주세요." buttons {"확인"} default button 1 with icon stop
		return
	end try

	-- 터미널에서 실행 (진행 상황이 보이도록)
	set cmd to "clear; /bin/zsh " & quoted form of runnerPath
	tell application "Terminal"
		activate
		do script cmd
	end tell
end run
