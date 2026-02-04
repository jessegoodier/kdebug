# kdebug bash completion
# Source this file or add to ~/.bashrc:
#   source <(kdebug --completions bash)
# Or:
#   source /path/to/completions/kdebug.bash

_kdebug_get_contexts() {
    kubectl config get-contexts -o name 2>/dev/null
}

_kdebug_get_namespaces() {
    local kubectl_args=$(_kdebug_get_kubectl_args)
    kubectl $kubectl_args get namespaces -o jsonpath='{.items[*].metadata.name}' 2>/dev/null
}

_kdebug_get_pods() {
    local ns="${1:-default}"
    local kubectl_args=$(_kdebug_get_kubectl_args)
    kubectl $kubectl_args get pods -n "$ns" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null
}

_kdebug_get_controllers() {
    local ns="${1:-default}"
    local controller_type="$2"
    local kubectl_args=$(_kdebug_get_kubectl_args)
    case "$controller_type" in
        deployment|deploy)
            kubectl $kubectl_args get deployments -n "$ns" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null
            ;;
        statefulset|sts)
            kubectl $kubectl_args get statefulsets -n "$ns" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null
            ;;
        daemonset|ds)
            kubectl $kubectl_args get daemonsets -n "$ns" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null
            ;;
    esac
}

_kdebug_get_kubectl_args() {
    local i args=""
    for ((i=1; i < ${#COMP_WORDS[@]}; i++)); do
        case "${COMP_WORDS[i]}" in
            --context)
                if [[ $((i+1)) -lt ${#COMP_WORDS[@]} ]]; then
                    args="$args --context=${COMP_WORDS[$((i+1))]}"
                fi
                ;;
            --context=*)
                args="$args ${COMP_WORDS[i]}"
                ;;
            --kubeconfig)
                if [[ $((i+1)) -lt ${#COMP_WORDS[@]} ]]; then
                    args="$args --kubeconfig=${COMP_WORDS[$((i+1))]}"
                fi
                ;;
            --kubeconfig=*)
                args="$args ${COMP_WORDS[i]}"
                ;;
        esac
    done
    echo "$args"
}

_kdebug_get_namespace_from_args() {
    local i
    for ((i=1; i < ${#COMP_WORDS[@]}; i++)); do
        case "${COMP_WORDS[i]}" in
            -n|--namespace)
                if [[ $((i+1)) -lt ${#COMP_WORDS[@]} ]]; then
                    echo "${COMP_WORDS[$((i+1))]}"
                    return
                fi
                ;;
            -n=*|--namespace=*)
                echo "${COMP_WORDS[i]#*=}"
                return
                ;;
        esac
    done
    local kubectl_args=$(_kdebug_get_kubectl_args)
    kubectl $kubectl_args config view --minify -o jsonpath='{..namespace}' 2>/dev/null || echo "default"
}

_kdebug_get_controller_from_args() {
    local i
    for ((i=1; i < ${#COMP_WORDS[@]}; i++)); do
        case "${COMP_WORDS[i]}" in
            --controller)
                if [[ $((i+1)) -lt ${#COMP_WORDS[@]} ]]; then
                    echo "${COMP_WORDS[$((i+1))]}"
                    return
                fi
                ;;
            --controller=*)
                echo "${COMP_WORDS[i]#*=}"
                return
                ;;
        esac
    done
}

_kdebug() {
    local cur prev words cword
    _init_completion || return

    local opts="--pod --controller --controller-name -n --namespace --context --kubeconfig
                --container --debug-image --cmd --cd-into --backup --compress --as-root
                --debug --completions -V --version --help -h"

    local controller_types="deployment deploy statefulset sts daemonset ds"

    case "$prev" in
        -n|--namespace)
            COMPREPLY=($(compgen -W "$(_kdebug_get_namespaces)" -- "$cur"))
            return
            ;;
        --context)
            COMPREPLY=($(compgen -W "$(_kdebug_get_contexts)" -- "$cur"))
            return
            ;;
        --kubeconfig)
            _filedir
            return
            ;;
        --pod)
            local ns=$(_kdebug_get_namespace_from_args)
            COMPREPLY=($(compgen -W "$(_kdebug_get_pods "$ns")" -- "$cur"))
            return
            ;;
        --controller)
            COMPREPLY=($(compgen -W "$controller_types" -- "$cur"))
            return
            ;;
        --controller-name)
            local ns=$(_kdebug_get_namespace_from_args)
            local ct=$(_kdebug_get_controller_from_args)
            if [[ -n "$ct" ]]; then
                COMPREPLY=($(compgen -W "$(_kdebug_get_controllers "$ns" "$ct")" -- "$cur"))
            fi
            return
            ;;
        --container|--debug-image|--cmd|--cd-into|--backup)
            # These take arbitrary values, no completion
            return
            ;;
        --completions)
            COMPREPLY=($(compgen -W "bash zsh" -- "$cur"))
            return
            ;;
    esac

    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "$opts" -- "$cur"))
        return
    fi
}

complete -F _kdebug kdebug

