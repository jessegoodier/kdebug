# kdebug - Universal Kubernetes Debug Container Utility

A CLI utility for launching ephemeral debug containers in Kubernetes pods with backup capabilities.

Useful for debugging and backups of containers that do not have a shell or other debugging tools.

## Features

- 🚀 Launch debug containers in any Kubernetes pod, with a nice shell environment (zsh or bash)
- 📦 Backup files/directories from pods (compressed or uncompressed)
- 🎨 Colorful kubecolor-style output
- 🛡️ Run as root with `--as-root` flag
- 📂 Change into expected directories with `--cd-into` (so you don't have to remember /proc/1/root)
- 🍻 Use any container image (defaults to a large alpine image that includes a lot of common debugging tools [https://github.com/jessegoodier/toolbox](https://github.com/jessegoodier/toolbox)

## Installation

### Using Homebrew (Recommended)

#### Option 1: Install from this tap (local development)


```bash
# Add the tap
brew tap jessegoodier/kdebug

# Install kdebug
brew install kdebug
```

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/jessegoodier/kdebug.git
cd kdebug

# Make executable and add to PATH
chmod +x bin/kdebug
sudo ln -s $(pwd)/bin/kdebug /usr/local/bin/kdebug
```

## Requirements

- Python 3.11+
- kubectl (configured with cluster access)

## Usage

### Interactive Sessions

```bash
# Interactive session with a specific pod
kdebug -n kubecost --pod aggregator-0 --container aggregator

# Using a StatefulSet
kdebug -n kubecost --controller sts --controller-name aggregator --container aggregator --cmd bash

# Using a Deployment
kdebug -n myapp --controller deployment --controller-name frontend --cmd sh

# Change into a specific directory
kdebug -n myapp --pod mypod-0 --cd-into /var/configs

# Run as root user
kdebug -n myapp --pod mypod-0 --as-root
```

### Backup Operations

```bash
# Direct copy (uncompressed) - faster for small files
kdebug -n myapp --pod mypod-0 --backup /var/configs

# Compressed backup - better for large files/directories
kdebug -n myapp --pod mypod-0 --backup /var/configs --compress
```

Backups are saved to `./backups/{namespace}/{timestamp}_{pod_name}[.tar.gz]`

### Options

```
Pod Selection:
  --pod POD                    Pod name (direct selection)
  --controller {deployment,deploy,statefulset,sts,daemonset,ds}
                              Controller type
  --controller-name NAME       Controller name (required with --controller)

Configuration:
  -n, --namespace NAMESPACE    Kubernetes namespace (default: current context)
  --container CONTAINER        Target container name
  --debug-image IMAGE          Debug container image (default: ghcr.io/jessegoodier/toolbox:latest)

Operations:
  --cmd CMD                    Command to run (default: bash)
  --cd-into PATH              Start shell in specified directory
  --backup PATH               Create backup of specified path
  --compress                  Compress backup with tar.gz (only with --backup)
  --as-root                   Run debug container as root user (UID 0)

Utility:
  --debug                     Enable debug mode (show kubectl commands)
```

## How It Works

1. **Launches an ephemeral debug container** in the target pod
2. **Shares process namespace** with the target container
3. **Provides interactive shell** or performs backup operations
4. **Automatically cleans up** the debug container when done

## Examples

### Debug a crashing pod

```bash
kdebug -n production --pod api-server-0 --container api --cmd bash
```

### Backup configuration files

```bash
# Uncompressed (faster)
kdebug -n production --pod api-server-0 --backup /etc/app/config

# Compressed (saves bandwidth)
kdebug -n production --pod api-server-0 --backup /var/log --compress
```

### Inspect a deployment's first pod

```bash
kdebug -n staging --controller deploy --controller-name web-app
```

### Run commands as root

```bash
kdebug -n production --pod db-0 --as-root --cmd "apt-get update && apt-get install -y tcpdump"
```

## Development

### Project Structure

```
kdebug/
├── bin/
│   └── kdebug              # Main executable
├── Formula/
│   └── kdebug.rb          # Homebrew formula
├── README.md              # This file
└── VERSION                # Version tracking
```

### Creating a Homebrew Tap

To publish this as a Homebrew tap:

1. Create a GitHub repository named `homebrew-kdebug`
2. Push this code to the repository
3. Create a release with a tag (e.g., `v0.1.0`)
4. Update the `url` and `sha256` in `Formula/kdebug.rb`

Users can then install with:
```bash
brew tap jessegoodier/kdebug
brew install kdebug
```

## License

MIT

## Author

Jesse Goodier

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.