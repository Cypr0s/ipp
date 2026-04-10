
PROJ=dokumentace


$(PROJ).pdf: $(PROJ).tex
	pdflatex -interaction=nonstopmode $(PROJ).tex
	pdflatex -interaction=nonstopmode $(PROJ).tex

clean:
	rm -f $(PROJ).aux $(PROJ).dvi $(PROJ).log $(PROJ).ps $(PROJ).out
# VS Code automated compilation files	
	rm -f $(PROJ).fdb_latexmk $(PROJ).fls $(PROJ).*.gz

clean-all: clean
	rm -f $(PROJ).pdf