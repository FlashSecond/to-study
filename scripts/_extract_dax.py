import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from content_collector import ContentCollector
c = ContentCollector()
result = c.collect_and_save(
    r'D:\Mylibrary\教程文档\dax.pdf',
    r'D:\Mylibrary\书籍总结\DAX-深度教材-v5.0-20260618-1902\_collected'
)
print(f'Title: {result.title}')
print(f'Pages: {result.metadata.get("pages", 0)}')
print(f'Chars: {len(result.content)}')
print(f'Error: {result.error}')
