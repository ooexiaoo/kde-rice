export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"

export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME=""
plugins=(git z zsh-autosuggestions zsh-syntax-highlighting)
source $ZSH/oh-my-zsh.sh

eval "$(starship init zsh)"
fpath+=(/usr/share/zsh/5.9/functions)

# System info on terminal start
fastfetch
export PATH=$PATH:/usr/local/go/bin
