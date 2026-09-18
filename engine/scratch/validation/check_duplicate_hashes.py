from pathlib import Path
import hashlib

folder1 = Path(r"C:\Users\USER\Desktop\Attachment\01_scraped_documents")
folder2 = Path(r"C:\Users\USER\Desktop\Attachment\02_scrapped_documents")

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

different = []
same = []

files1 = {f.name: f for f in folder1.iterdir() if f.is_file()}
files2 = {f.name: f for f in folder2.iterdir() if f.is_file()}

for name in files1.keys() & files2.keys():
    h1 = sha256(files1[name])
    h2 = sha256(files2[name])

    if h1 == h2:
        same.append(name)
    else:
        different.append(name)

print("Same content:", len(same))
print("Different content:", len(different))

print("\nExamples of different:")
for x in different[:10]:
    print(x)