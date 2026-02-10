# kdebug demo interactive debug container — VHS Tape

Output vhs/kdebug-demo_tui.gif

Set Shell zsh
Set Width 1200
Set Height 1000
Set WindowBar Colorful
# Set MarginFill "#0a1667"
# Set Margin 20
Set BorderRadius 14
Hide
Type "autoload -U colors && colors && clear"
Enter

# Set your prompt variable
Type 'PROMPT="%{$fg[yellow]%}(minikube)%{$reset_color%} %{$fg_bold[green]%}~/kdebug%{$reset_color%} $ "'
Enter
Type "clear"
Enter
Show

# ─── Scene: Interactive TUI Pod Selection ───

Ctrl+L
Sleep 500ms
Type "kdebug --cd-into /var/configs"
Enter
Sleep 1s

Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Down
Sleep 300ms
Enter
Sleep 4s

Type "du -h -d1"
Enter
Sleep 4s
Screenshot vhs/kdebug-demo_tui.png
Sleep .1s
