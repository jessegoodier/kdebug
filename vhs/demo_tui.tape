# kdebug Demo — VHS Tape
# Run: vhs demo.tape
# Produces: demo.gif

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

# # ─── Scene: Direct Pod Debug Session ───

# Ctrl+L
# Sleep 500ms
# Type "kdebug -n toolbox --pod toolbox"
# Enter
# Sleep 10s

# Type "hostname"
# Enter
# Sleep 2s

# Type "ls /proc/1/root/"
# Enter
# Sleep 2s

# Type "ps aux"
# Enter
# Sleep 3s

# Type "exit"
# Enter
# Sleep 5s

# # ─── Scene: Backup with Compression ───

# Ctrl+L
# Sleep 500ms
# Type "kdebug -n toolbox --pod toolbox --backup /etc/hostname --compress"
# Enter
# Sleep 15s

# # ─── Scene: Debug Mode (Verbose) ───

# Ctrl+L
# Sleep 500ms
# Set TypingSpeed 50ms
# Type "kdebug -n toolbox --pod toolbox --debug --cmd 'echo hello from debug container'"
# Set TypingSpeed 40ms
# Enter
# Sleep 15s

# Sleep 3s
