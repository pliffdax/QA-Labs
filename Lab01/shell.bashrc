# Settings for the recorded QA shell; keep its dedicated history files.
case "$TERM" in
    xterm*|screen*|tmux*|rxvt*|linux)
        PS1='QA01 \[\e[01;32m\]\u@\h\[\e[00m\]:\[\e[01;34m\]\w\[\e[00m\]\$ '
        alias ls='ls --color=auto'
        alias grep='grep --color=auto'
        ;;
    *) PS1='QA01 \u@\h:\w\$ ' ;;
esac
shopt -s histappend
PROMPT_COMMAND='history -a'
