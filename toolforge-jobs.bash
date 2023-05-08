_toolforge_jobs() {
	local cur="${COMP_WORDS[COMP_CWORD]}"
	local prev="${COMP_WORDS[COMP_CWORD-1]}"
	COMPREPLY=()

	local cur_index="$COMP_CWORD"
	local subcmd_index=1
	if [[ "$TOOLFORGE_CLI" == "1" ]]; then
		cur_index=$((cur_index - 1))
		subcmd_index=2
	fi

	case "$cur_index" in
		1)
			if [[ $cur == -* ]]; then
				COMPREPLY=($(compgen -W "--help" -- ${cur}))
			else
				COMPREPLY=($(compgen -W "images run show list delete flush load restart" -- ${cur}))
			fi
			;;
		**)
			case "${COMP_WORDS[subcmd_index]}" in
				images)
					COMPREPLY=()
					;;
				run)
					case "$prev" in
						--command)
							COMPREPLY=()
							;;
						--image)
							# TODO: autocomplete images
							COMPREPLY=()
							;;
						-o|--filelog-stdout|-e|--filelog-stderr)
							COMPREPLY=($(compgen -A file -- ${cur}))
							;;
						--retry)
							COMPREPLY=()
							;;
						--mem)
							COMPREPLY=()
							;;
						--cpu)
							COMPREPLY=()
							;;
						--emails)
							COMPREPLY=($(compgen -W "none all onfinish onfailure" -- ${cur}))
							;;
						--schedule)
							COMPREPLY=()
							;;
						**)
							local options="--command --image --no-filelog -o --filelog-stdout -e --filelog-stderr --retry --mem --cpu --emails --schedule --continuous --wait"
							local i=$((subcmd_index + 1))
							while ((i<COMP_CWORD)); do
								if [[ "${COMP_WORDS[i]}" == "--command" ]]; then
									options="${options/--command/}"
								elif [[ "${COMP_WORDS[i]}" == "--image" ]]; then
									options="${options/--image/}"
								elif [[ "${COMP_WORDS[i]}" == "--no-filelog" ]]; then
									options="${options/--no-filelog/}"
									options="${options/-o/}"
									options="${options/--filelog-stdout/}"
									options="${options/-e/}"
									options="${options/--filelog-stderr/}"
								elif [[ "${COMP_WORDS[i]}" == "-o" || "${COMP_WORDS[i]}" == "--filelog-stdout" ]]; then
									options="${options/--no-filelog/}"
									options="${options/-o/}"
									options="${options/--filelog-stdout/}"
								elif [[ "${COMP_WORDS[i]}" == "-e" || "${COMP_WORDS[i]}" == "--filelog-stderr" ]]; then
									options="${options/--no-filelog/}"
									options="${options/-e/}"
									options="${options/--filelog-stderr/}"
								elif [[ "${COMP_WORDS[i]}" == "--retry" ]]; then
									options="${options/--retry/}"
								elif [[ "${COMP_WORDS[i]}" == "--mem" ]]; then
									options="${options/--mem/}"
								elif [[ "${COMP_WORDS[i]}" == "--cpu" ]]; then
									options="${options/--cpu/}"
								elif [[ "${COMP_WORDS[i]}" == "--emails" ]]; then
									options="${options/--emails/}"
								elif [[ "${COMP_WORDS[i]}" == "--schedule" || "${COMP_WORDS[i]}" == "--continuous" || "${COMP_WORDS[i]}" == "--wait" ]]; then
									options="${options/--schedule/}"
									options="${options/--continuous/}"
									options="${options/--wait/}"
								fi

								((++i))
							done

							COMPREPLY=($(compgen -W "${options}" -- ${cur}))
							;;
						esac
					;;
				show)
					if [ "$cur_index" = "2" ]; then
						COMPREPLY=($(compgen -W "$(toolforge jobs list -o name)" -- ${cur}))
					else
						COMPREPLY=()
					fi
					;;
				list)
					case "$prev" in
						-o|--output)
							COMPREPLY=($(compgen -W "normal long name" -- ${cur}))
							;;
						**)
							local options="-o --output"
							local i=$((subcmd_index + 1))
							while ((i<COMP_CWORD)); do
								if [[ "${COMP_WORDS[i]}" == "-o" || "${COMP_WORDS[i]}" == "--output" ]]; then
									options="${options/-o/}"
									options="${options/--output/}"
								fi

								((++i))
							done

							COMPREPLY=($(compgen -W "${options}" -- ${cur}))
							;;
						esac
					;;
				delete)
					if [ "$cur_index" = "2" ]; then
						COMPREPLY=($(compgen -W "$(toolforge jobs list -o name)" -- ${cur}))
					else
						COMPREPLY=()
					fi
					;;
				flush)
					COMPREPLY=()
					;;
				load)
					if [ "$cur_index" = "2" ]; then
						COMPREPLY=($(compgen -A file -- ${cur}))
					else
						COMPREPLY=()
					fi
					;;
				restart)
					if [ "$cur_index" = "2" ]; then
						COMPREPLY=($(compgen -W "$(toolforge jobs list -o name)" -- ${cur}))
					else
						COMPREPLY=()
					fi
					;;
				**)
					COMPREPLY=()
					;;
			esac
			;;
	esac
}

complete -F _toolforge_jobs toolforge-jobs
