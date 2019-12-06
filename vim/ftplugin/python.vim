setlocal tabstop=4
setlocal softtabstop=4
setlocal shiftwidth=4
setlocal textwidth=80
setlocal smarttab
setlocal expandtab
setlocal smartindent

let python_highlight_all = 1

" Add jumping into library files (hit gf on an import)
python << EOF
import os
import sys
import vim
for p in sys.path:
	if os.path.isdir(p):
		vim.command(r"set path+=%s" % (p.replace(" ", r"\ ")))
EOF

" Add tags support, regenerate with :
" ctags -R -f ~/.vim/tags/python.ctags /usr/lib/python2.5/
set tags+=$HOME/.vim/tags/python.ctags

" Code Completion
set omnifunc=pythoncomplete#Complete
