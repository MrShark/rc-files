filetype off

call pathogen#infect()
call pathogen#helptags()

filetype plugin indent on
syntax on

set showcmd            " Show (partial) command in status line.
set showmatch          " Show matching brackets.
set incsearch          " Incremental search
set autowrite          " Automatically save before commands like :next and :make
set hidden             " Hide buffers when they are abandoned
set nocompatible 
set textwidth=120
set bkc=auto,breakhardlink
set tabstop=4
set shiftwidth=4
set expandtab
set scrolloff=5
let mapleader = "*"
set wildmode=longest,list,full
set wildmenu
behave xterm


autocmd FileType javascript set omnifunc=javascriptcomplete#CompleteJS
autocmd FileType html set omnifunc=htmlcomplete#CompleteTags
autocmd FileType css set omnifunc=csscomplete#CompleteCSS


augroup filetypedetect 
autocmd BufNewFile,BufRead *.pde setf arduino
autocmd BufNewFile,BufRead *.sage setf python
" Taken from http://en.wikipedia.org/wiki/Wikipedia:Text_editor_support#Vim
" 	Ian Tegebo <ian.tegebo@gmail.com>
autocmd BufNewFile,BufRead *.wiki setf Wikipedia
augroup END 


inoremap <Nul> <C-x><C-o>

" add spell checking on \s (from  http://www.highley-recommended.com/text-processing.html)
map <Leader>s <Esc>:!aspell -c --dont-backup "%"<CR>:e! "%"<CR><CR>
map > :lnext<CR>
map < :lprevious<CR>

" Alt+leftarrow will go one window left, etc. (from http://vim.wikia.com/wiki/Switch_between_Vim_window_splits_easily )
nmap <silent> <A-Up> :wincmd k<CR>
nmap <silent> <A-Down> :wincmd j<CR>
nmap <silent> <A-Left> :wincmd h<CR>
nmap <silent> <A-Right> :wincmd l<CR>

set hlsearch

let g:pymode_lint_unmodified = 1
let g:pymode_options_max_line_length = 120
let g:pymode_lint_options_pep8 =
        \ {'max_line_length': g:pymode_options_max_line_length}
let g:pymode_rope = 0

" set default colors
colorscheme jens
