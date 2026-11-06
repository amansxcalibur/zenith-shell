# fish completion for zenith-shell
set -l setup_commands install sync update doctor uninstall logs

complete -c zenith-shell -f
complete -c zenith-shell -n __fish_use_subcommand -a start -d 'Start the shell'
complete -c zenith-shell -n __fish_use_subcommand -a stop -d 'Stop the shell'
complete -c zenith-shell -n __fish_use_subcommand -a restart -d 'Restart the shell'
complete -c zenith-shell -n __fish_use_subcommand -a status -d 'Show whether the shell is running'
complete -c zenith-shell -n __fish_use_subcommand -a lock -d 'Lock the screen'
complete -c zenith-shell -n __fish_use_subcommand -a settings -d 'Open the settings window'
complete -c zenith-shell -n __fish_use_subcommand -a setup -d 'Install, update or remove Zenith Shell'
complete -c zenith-shell -n __fish_use_subcommand -a help -d 'Show help'
complete -c zenith-shell -n __fish_use_subcommand -l help -d 'Show help'
complete -c zenith-shell -n __fish_use_subcommand -l version -d 'Show the installed version'

complete -c zenith-shell -n '__fish_seen_subcommand_from lock' -s f -d 'Return once locked'

set -l in_setup "__fish_seen_subcommand_from setup; and not __fish_seen_subcommand_from $setup_commands"
complete -c zenith-shell -n $in_setup -a install -d 'Full install'
complete -c zenith-shell -n $in_setup -a sync -d 'Install what is missing and configure the selected WMs'
complete -c zenith-shell -n $in_setup -a update -d 'Pull the latest version and re-apply setup'
complete -c zenith-shell -n $in_setup -a doctor -d 'Check dependencies and setup'
complete -c zenith-shell -n $in_setup -a uninstall -d 'Remove Zenith Shell'
complete -c zenith-shell -n $in_setup -a logs -d 'Show the end of the installer log'

complete -c zenith-shell -n '__fish_seen_subcommand_from install sync update doctor' -l wm -x -a 'auto i3 sway all' -d 'Window manager to set up'
complete -c zenith-shell -n '__fish_seen_subcommand_from install sync update uninstall' -l dry-run -d 'Show the plan without changing anything'
complete -c zenith-shell -n '__fish_seen_subcommand_from install sync update uninstall' -s y -l yes -d 'Never ask for confirmation'
complete -c zenith-shell -n '__fish_seen_subcommand_from install sync update uninstall' -s v -l verbose -d 'Show command output as it runs'
complete -c zenith-shell -n '__fish_seen_subcommand_from uninstall' -l purge -d 'Also remove tools built from source'
complete -c zenith-shell -n '__fish_seen_subcommand_from logs' -s n -l lines -x -d 'Number of lines to show'
