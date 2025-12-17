from bs4 import BeautifulSoup

# Load the TTML2 file
with open('s.ttml2', 'r', encoding='utf-8') as ttml_file:
    ttml_content = ttml_file.read()

# Parse TTML2 with BeautifulSoup
soup = BeautifulSoup(ttml_content, 'xml')

# Extract subtitles and convert to SRT format
srt_lines = []
counter = 1

for p in soup.find_all('p'):
    begin = p.get('begin')
    end = p.get('end')
    text = p.get_text(strip=True, separator='\n')
    
    if begin and end and text:
        # Format timestamps from HH:MM:SS.mmm to HH:MM:SS,mmm
        begin = begin.replace('.', ',')
        end = end.replace('.', ',')
        
        srt_lines.append(str(counter))
        srt_lines.append(f'{begin} --> {end}')
        srt_lines.append(text)
        srt_lines.append('')  # Empty line between entries
        counter += 1

# Join lines and write to SRT file
srt_content = '\n'.join(srt_lines)
with open('output.srt', 'w', encoding='utf-8') as srt_file:
    srt_file.write(srt_content)

print("Conversion completed successfully.")