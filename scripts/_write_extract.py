import os
OUT = r'D:\Mylibrary\书籍总结\DAX-深度教材-v5.0-20260618-1902'
content = open(os.path.join(OUT,'..', '..', '..', '..', '..', '.qclaw','skills','to-study','scripts','_提炼_dax_content.txt'),'r',encoding='utf-8').read()
open(os.path.join(OUT,'_提炼清单.md'),'w',encoding='utf-8').write(content)
print('Done')
