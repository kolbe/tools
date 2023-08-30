#!/usr/bin/env python3

import os
import sys
import pycpdflib as pdf

pdf.loadDLL("libpycpdf.so")

source_filename = sys.argv[1]
source_pdf = pdf.fromFile(source_filename, '')
new_filename = os.path.splitext(source_filename)
new_filename = new_filename[0]+'_booklet'+new_filename[1]

pdf.padMultiple(source_pdf, 4)

num_pages = pdf.pages(source_pdf)
print(num_pages)

pages=[]

i=0
while i < num_pages/2:
    if i%2 == 1: pages.append(i+1)
    pages.append(num_pages-i)
    if i%2 == 0: pages.append(i+1)
    i+=1

page_order = ",".join(str(page) for page in pages)

r = pdf.parsePagespec(source_pdf, page_order)

new_pdf = pdf.selectPages(source_pdf, r)

pdf.toFile(new_pdf, new_filename, True, True)
