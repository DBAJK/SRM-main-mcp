import os
import time
import re
from colorama import init, Fore, Style

# Initialize colorama for colored terminal output
init()

# Path to the file
file_path = "5G-Network-Slicing/slicesim/Graph.py"

# Read the file content
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all occurrences of the pattern we want to replace
pattern = r"(\s+)ax\.yaxis\.set_major_formatter"
matches = re.finditer(pattern, content)

# Store the matches for visualization
matches_info = []
for match in matches:
    line_start = content[:match.start()].count('\n') + 1
    line_content = content.split('\n')[line_start-1]
    indent_level = len(match.group(1))
    matches_info.append({
        'line_number': line_start,
        'content': line_content,
        'indent': indent_level
    })

print(f"{Fore.CYAN}Found {len(matches_info)} occurrences of 'ax.yaxis.set_major_formatter' in {file_path}{Style.RESET_ALL}")
print()

# Display before state
print(f"{Fore.YELLOW}=== BEFORE CHANGE ==={Style.RESET_ALL}")
for idx, match in enumerate(matches_info):
    line_num = match['line_number']
    content = match['content']
    print(f"{Fore.GREEN}{line_num:4d}{Style.RESET_ALL}: {content}")
print()

# Start the visual transformation
print(f"{Fore.YELLOW}=== TRANSFORMATION PROCESS ==={Style.RESET_ALL}")
print("Starting in 3 seconds...")
time.sleep(3)

# Prepare the after content
after_content = re.sub(
    r"                    ax\.yaxis\.set_major_formatter", 
    r"        ax.yaxis.set_major_formatter", 
    content
)

# Find the affected lines in the after content
after_lines = after_content.split('\n')
before_lines = content.split('\n')

# Show the transformation for each occurrence
for idx, match in enumerate(matches_info):
    line_num = match['line_number']
    before = before_lines[line_num - 1]
    after = after_lines[line_num - 1]
    
    # Only show the transformation if this line is actually affected
    if "                    ax.yaxis.set_major_formatter" in before:
        print(f"\n{Fore.BLUE}Transforming line {line_num}:{Style.RESET_ALL}")
        print(f"{Fore.RED}BEFORE{Style.RESET_ALL}: {before}")
        
        # Animate the transformation
        for i in range(len(before)):
            if i < len(after):
                print("\r" + before[:i] + after[i] + before[i+1:], end="")
            else:
                print("\r" + before[:i] + before[i:], end="")
            time.sleep(0.05)
        
        print("\r" + after)
        print(f"{Fore.GREEN}AFTER{Style.RESET_ALL} : {after}")
        time.sleep(1)

print(f"\n{Fore.YELLOW}=== AFTER CHANGE ==={Style.RESET_ALL}")
for idx, match in enumerate(matches_info):
    line_num = match['line_number']
    content = after_lines[line_num - 1]
    print(f"{Fore.GREEN}{line_num:4d}{Style.RESET_ALL}: {content}")

print(f"\n{Fore.CYAN}Transformation complete!{Style.RESET_ALL}") 