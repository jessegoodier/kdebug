# kdebug fish completion
# Install: kdebug --completions fish | source
# Or: kdebug --completions fish > ~/.config/fish/completions/kdebug.fish

function __kdebug_get_kubectl_args
    set -l tokens (commandline -opc)
    set -l args
    set -l i 2
    while test $i -le (count $tokens)
        switch $tokens[$i]
            case --context
                set -l next (math $i + 1)
                if test $next -le (count $tokens)
                    set -a args --context=$tokens[$next]
                end
            case '--context=*'
                set -a args $tokens[$i]
            case --kubeconfig
                set -l next (math $i + 1)
                if test $next -le (count $tokens)
                    set -a args --kubeconfig=$tokens[$next]
                end
            case '--kubeconfig=*'
                set -a args $tokens[$i]
        end
        set i (math $i + 1)
    end
    echo $args
end

function __kdebug_get_namespace_from_args
    set -l tokens (commandline -opc)
    set -l i 2
    while test $i -le (count $tokens)
        switch $tokens[$i]
            case -n --namespace
                set -l next (math $i + 1)
                if test $next -le (count $tokens)
                    echo $tokens[$next]
                    return
                end
            case '-n=*' '--namespace=*'
                string replace -r '^[^=]+=' '' $tokens[$i]
                return
        end
        set i (math $i + 1)
    end
    set -l kubectl_args (__kdebug_get_kubectl_args)
    set -l ns (kubectl $kubectl_args config view --minify -o jsonpath='{..namespace}' 2>/dev/null)
    if test -n "$ns"
        echo $ns
    else
        echo default
    end
end

function __kdebug_get_contexts
    kubectl config get-contexts -o name 2>/dev/null
end

function __kdebug_get_namespaces
    set -l kubectl_args (__kdebug_get_kubectl_args)
    kubectl $kubectl_args get namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null
end

function __kdebug_get_pods
    set -l ns (__kdebug_get_namespace_from_args)
    set -l kubectl_args (__kdebug_get_kubectl_args)
    kubectl $kubectl_args get pods -n "$ns" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null
end

function __kdebug_get_controllers
    set -l ns (__kdebug_get_namespace_from_args)
    set -l kubectl_args (__kdebug_get_kubectl_args)
    set -l cur (commandline -ct)

    if string match -q '*/*' -- "$cur"
        # User typed TYPE/ - complete the name part
        set -l ct (string replace -r '/.*' '' -- "$cur")
        set -l resource
        switch $ct
            case deployment deploy
                set resource deployments
            case statefulset sts
                set resource statefulsets
            case daemonset ds
                set resource daemonsets
            case '*'
                return
        end
        for name in (kubectl $kubectl_args get "$resource" -n "$ns" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null)
            echo "$ct/$name"
        end
    else
        # Complete type prefixes
        printf '%s\n' deployment/ deploy/ statefulset/ sts/ daemonset/ ds/
    end
end

# Disable file completions for kdebug
complete -c kdebug -f

# Target selection
complete -c kdebug -l pod -d 'Pod name for direct selection' -xa '(__kdebug_get_pods)'
complete -c kdebug -l controller -d 'Controller as TYPE/NAME' -xa '(__kdebug_get_controllers)'

# Options
complete -c kdebug -s n -l namespace -d 'Kubernetes namespace' -xa '(__kdebug_get_namespaces)'
complete -c kdebug -l context -d 'Kubernetes context to use' -xa '(__kdebug_get_contexts)'
complete -c kdebug -l kubeconfig -d 'Path to kubeconfig file' -rF
complete -c kdebug -l container -d 'Target container for process namespace sharing' -x
complete -c kdebug -l debug-image -d 'Debug container image' -x
complete -c kdebug -l cmd -d 'Command to run in debug container' -x
complete -c kdebug -l cd-into -d 'Change to directory on start' -rF
complete -c kdebug -l container-path -d 'Path inside the container to back up' -x
complete -c kdebug -l local-path -d 'Local destination (supports {namespace},{pod},{date},{container})' -x
complete -c kdebug -l compress -d 'Compress backup as tar.gz'
complete -c kdebug -l tar-exclude -d 'Exclude path from compressed backup (repeatable)' -x
complete -c kdebug -l as-root -d 'Run debug container as root'
complete -c kdebug -l verbose -d 'Show kubectl commands being executed'
complete -c kdebug -l completions -d 'Output shell completion script' -xa 'bash zsh fish'
complete -c kdebug -s v -l version -d 'Show version and exit'
complete -c kdebug -s h -l help -d 'Show help message'
