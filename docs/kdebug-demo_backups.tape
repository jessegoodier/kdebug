# kdebug demo backups — VHS Tape

Output docs/kdebug-demo_backups.gif

Set Shell zsh
Set Width 1600
Set Height 1200
Set WindowBar Colorful
Hide
Type "autoload -U colors && colors && clear"
Enter
# Set your prompt variable
Type 'PROMPT="%{$fg[yellow]%}(minikube)%{$reset_color%} %{$fg_bold[green]%}~/kdebug%{$reset_color%} $ "'
Enter
Type "rm -rf ./backups/kubecost/"
Enter
Type "clear"
Enter

# ─── Scene: Interactive TUI Pod Selection ───

Ctrl+L
# show that no files are in the backup directory

Type "echo 'No files exist in the backup directory yet...'"
Sleep 1s
Enter
Show
Sleep 2s
Type "ls -lah ./backups/"
Enter
Sleep 3s

# run the backup command for the kubecost-local-store deployment, which will copy files from the container to the local backup directory
Type "kdebug backup --container-path /var/configs --pod kubecost-aggregator-0 \"
Enter
Type "  --compress --tar-exclude waterfowl --tar-exclude values"
Enter
Sleep 12s

# show that files have been copied to the backup directory
Type "ls -lah ./backups/kubecost/"
Enter
Screenshot docs/kdebug-demo_backups.png
Sleep 15s
