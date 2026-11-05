# bash completion for zenith-shell
_zenith_shell() {
    local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
    local seen=" ${COMP_WORDS[*]:1:COMP_CWORD-1} " subcommand="" word opts

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=($(compgen -W "start stop restart status lock setup help --help --version" -- "$cur"))
        return
    fi

    case ${COMP_WORDS[1]} in
        lock)
            [[ $seen == *" -f "* ]] || COMPREPLY=($(compgen -W "-f" -- "$cur"))
            return
            ;;
        setup) ;;
        *) return ;;
    esac

    if [[ $prev == --wm ]]; then
        COMPREPLY=($(compgen -W "auto i3 sway all" -- "$cur"))
        return
    fi

    for word in install sync update doctor uninstall logs; do
        if [[ $seen == *" $word "* ]]; then
            subcommand=$word
            break
        fi
    done

    if [[ -z $subcommand ]]; then
        if [[ $cur == -* ]]; then
            COMPREPLY=($(compgen -W "--help" -- "$cur"))
        else
            COMPREPLY=($(compgen -W "install sync update doctor uninstall logs" -- "$cur"))
        fi
        return
    fi

    case $subcommand in
        install | sync | update) opts="--wm --dry-run --yes --verbose" ;;
        doctor) opts="--wm" ;;
        uninstall) opts="--dry-run --purge --yes --verbose" ;;
        logs) opts="--lines" ;;
    esac
    COMPREPLY=($(compgen -W "$opts --help" -- "$cur"))
}
complete -F _zenith_shell zenith-shell
