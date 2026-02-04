# kdebug - Universal Kubernetes Debug and File Copy Container Utility

Simple utility for launching ephemeral debug containers in Kubernetes pods with interactive shell access, backup capabilities, and a colorful TUI for pod selection.

Similar to kpf <https://github.com/jessegoodier/kpf>, this is a python wrapper around `kubectl debug` and `kubectl cp`.

## Features

- 🐚 **Interactive Shell Access** - Launch bash/zsh sessions in debug containers directly to the directory of your choice
- 💾 **Backup Capabilities** - Copy files/directories from pods with optional compression
- 🔍 **Multiple Selection Modes** - Direct pod, controller-based, or interactive tui
- 🎯 **Smart Container Selection** - Auto-select containers or choose specific targets
- 🔐 **Root Access Support** - Run debug containers as root when needed
- 📦 **Controller Support** - Works with Deployments, StatefulSets, and DaemonSets

## Installation

```bash
brew install jessegoodier/kdebug/kdebug
```

Or

```bash
# Clone the repository
git clone https://github.com/jessegoodier/kdebug.git
cd kdebug
```

Then make it is executable and add to something in your PATH

```
chmod +x bin/kdebug
ln -s $(pwd)/bin/kdebug ~/.local/bin/kdebug
```

## Shell Completion

kdebug supports tab completion for bash and zsh with dynamic lookups for namespaces, pods, and controller names.

### Bash

```bash
# Add to ~/.bashrc
source <(kdebug --completions bash)

# Or source the file directly
source /path/to/kdebug/completions/kdebug.bash
```

### Zsh

```bash
# Option 1: Source directly (add to ~/.zshrc)
source <(kdebug --completions zsh)

# Option 2: Install to fpath (recommended)
mkdir -p ~/.zsh/completions
kdebug --completions zsh > ~/.zsh/completions/_kdebug
# Add to ~/.zshrc before compinit:
fpath=(~/.zsh/completions $fpath)
autoload -Uz compinit && compinit
```

### Completion Features

- `kdebug --<TAB>` - Complete all options
- `kdebug -n <TAB>` - Complete namespace names from cluster
- `kdebug --pod <TAB>` - Complete pod names (respects -n flag)
- `kdebug --controller <TAB>` - Complete controller types
- `kdebug --controller sts --controller-name <TAB>` - Complete controller names
- `kdebug --context <TAB>` - Complete context names from kubeconfig
- `kdebug --kubeconfig <TAB>` - Complete file paths

## Usage

### Global Options

kdebug supports kubectl-compatible `--context` and `--kubeconfig` flags to target different clusters:

```bash
# Use a specific context
kdebug --context minikube -n default --pod my-pod

# Use a different kubeconfig file
kdebug --kubeconfig .kubeconfig -n openclaw

# Combine both options
kdebug --kubeconfig /path/to/config --context staging -n myapp --pod api-0
```

These options are passed to all kubectl commands, including those used for tab completion.

### Interactive Mode (TUI)

When no pod or controller is specified, kdebug launches an interactive menu system:

# Interactive mode - select from all resources in current namespace
```bash
kdebug
```

# Interactive mode with specific namespace

```bash
kdebug -n openclaw
```

**TUI Features:**
- ⬆️⬇️ Use arrow keys to navigate
- 1️⃣-9️⃣ Press numbers for quick selection
- ↩️ Press Enter to confirm
- ❌ Press 'q' to quit

The TUI displays all pods in the namespace with:
- Color-coded status indicators (Green=Running, Yellow=Pending, etc.)
- Pod names highlighted for easy identification
- Real-time status information

### Direct Pod Selection

```bash
# Interactive session with direct pod
kdebug -n kubecost --pod aggregator-0 --container aggregator

# Auto-select first container if not specified
kdebug -n kubecost --pod aggregator-0

# Custom shell command
kdebug -n kubecost --pod aggregator-0 --cmd sh
```

### Controller-Based Selection

```bash
# Using StatefulSet (sts)
kdebug -n kubecost --controller sts --controller-name aggregator --container aggregator

# Using Deployment
kdebug -n myapp --controller deployment --controller-name frontend --cmd bash

# Using DaemonSet
kdebug -n logging --controller ds --controller-name fluentd
```

**Supported Controller Types:**
- `deployment` or `deploy` - Kubernetes Deployments
- `statefulset` or `sts` - StatefulSets
- `daemonset` or `ds` - DaemonSets

### Advanced Features

#### Change Directory on Start

```bash
# Start shell in specific directory
kdebug -n kubecost --pod aggregator-0 --cd-into /var/configs
```

#### Backup Mode

```bash
# Backup directory (uncompressed)
kdebug -n kubecost --pod aggregator-0 --backup /var/configs

# Backup with compression
kdebug -n kubecost --pod aggregator-0 --backup /var/configs --compress

# Backups are saved to: ./backups/<namespace>/<timestamp>_<pod-name>
```

#### Run as Root

```bash
# Launch debug container as root user
kdebug -n myapp --pod frontend-abc123 --as-root
```

#### Debug Mode

```bash
# Show all kubectl commands being executed
kdebug -n myapp --pod frontend-abc123 --debug
```

## Examples

### Example 1: Interactive Pod Selection

```bash
$ kdebug -n production

Starting interactive pod selection...

══════════════════════════════════════════════════════════════════════
Select Pod in namespace: production
══════════════════════════════════════════════════════════════════════

▶ 1. frontend-abc123 (Running)
  2. frontend-def456 (Running)
  3. backend-ghi789 (Running)
  4. database-0 (Running)
  5. worker-jkl012 (Pending)

──────────────────────────────────────────────────────────────────────
Use ↑/↓ arrows or numbers to select, Enter to confirm, q to quit
──────────────────────────────────────────────────────────────────────
```

### Example 2: Quick Debug Session

```bash
# Launch debug container and get bash shell
kdebug -n kubecost --controller sts --controller-name aggregator --container aggregator

# Output:
# ══════════════════════════════════════════════════════════════════════
# Starting interactive session in pod aggregator-0
# Container: debugger-xyz
# Command: bash
# ══════════════════════════════════════════════════════════════════════
```

### Example 3: Backup Configuration Files

```bash
# Backup with compression
kdebug -n production --pod api-server-0 --backup /etc/app/config --compress

# Output:
# ══════════════════════════════════════════════════════════════════════
# Creating backup from pod api-server-0
# Path: /etc/app/config
# Mode: Compressed (tar.gz)
# ══════════════════════════════════════════════════════════════════════
# ✓ Path exists: /etc/app/config
# ✓ Backup archive created
# ✓ Backup saved to: ./backups/production/2024-02-04_10-30-45_api-server-0.tar.gz
```

## Color Scheme

kdebug uses a kubecolor-inspired color scheme:

- 🔵 **Blue** - Borders and separators
- 🟢 **Green** - Success messages and running status
- 🟡 **Yellow** - Warnings and pending status
- 🔴 **Red** - Errors and failed status
- 🟣 **Magenta** - Namespaces
- 🔷 **Cyan** - Pod and container names
- ⚪ **White/Gray** - General text and metadata

## Requirements

- Python 3.6+
- kubectl configured with cluster access
- Kubernetes cluster with ephemeral containers support (v1.23+)

## How It Works

1. **Resource Discovery** - Queries Kubernetes API for controllers/pods
2. **Debug Container Launch** - Creates ephemeral container with debug image
3. **Process Sharing** - Enables `--share-processes` for full pod access
4. **Interactive Session** - Attaches to container with TTY
5. **Cleanup** - Terminates debug container after session ends

## Troubleshooting

### "Operation not supported on socket" Error

The interactive TUI requires a real terminal (TTY). Ensure you're running kdebug in:
- A standard terminal (not piped or redirected)
- Not through automation tools that don't provide TTY
- With proper terminal emulation support

### "Pod Security Policy" Warnings

If you see warnings about `runAsNonRoot`, the pod has security restrictions. Try:
- Running without `--as-root` flag
- Checking pod security policies
- Using a different debug image

### Container Won't Start

Check:
- Debug image is accessible from cluster
- Pod has sufficient resources
- Network policies allow image pull
- Use `--debug` flag to see kubectl commands

## License

MIT

## Contributing

Contributions welcome! Please open issues or pull requests.

---

Made with ❤️ and Bob