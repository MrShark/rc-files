" Vim color file

" This is the default color scheme.  It doesn't define the Normal
" highlighting, it uses whatever the colors used to be.

set background=dark
hi clear

" Load the syntax highlighting defaults, if it's enabled.
if exists("syntax_on")
   syntax reset
endif



let g:colors_name="jens"

" hi def otlLeadingSpaces ctermbg=darkred guibg=#500000
hi  otlTodo         ctermbg=DarkCyan
hi  otlTagRef       ctermbg=DarkCyan ctermfg=DarkRed cterm=bold
hi  otlTagDef       ctermbg=DarkCyan ctermfg=DarkRed cterm=bold
hi  otlTextLeader                   ctermfg=Black

hi  otlTab0         ctermfg=darkred             cterm=bold
hi  otlTab1         ctermfg=darkblue            cterm=bold
hi  otlTab2         ctermfg=darkmagenta         cterm=bold
hi  otlTab3         ctermfg=darkred             
hi  otlTab4         ctermfg=darkblue           
hi  otlTab5         ctermfg=darkmagenta       
hi  otlTab6         ctermfg=darkred             cterm=underline
hi  otlTab7         ctermfg=darkblue            cterm=underline
hi  otlTab8         ctermfg=darkmagenta         cterm=underline
hi  otlTab9         ctermfg=darkred             cterm=bold

