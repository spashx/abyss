The IlSpy application is a dotnet decompiler that provides several features.

The folder IlSpy contains the root application.

I need a detailled analysis on the "Search" features of the application, which provides mainly:
1) Search pane UI and model
2) Search result factory and filtering

# 1) MANDATORY - KNOWLEDGE BASE USAGE

For any information seach about ILSpy, ALWAYS USE IN PRIORITY the Abyss MCP server and its provided tools:

- list_documents - List all indexed documents
- query - Semantic search with multi-criteria filtering
- list_sources - List indexed sources and filter values
- list_filterable_fields - Describe filterable metadata fields

# 2) ACTIONS TO PERFORM

As a seasoned expert in C#/.NET programming and professionnal senior software architect, perform these tasks:

2.1) - search into the ABYSS knowledge base all entities (modules, classes, methods) implied with the " Search", "Search pane UI and model", "Search result factory and filtering". Identify the relations between this entities.

2.2) - identify the main workflows (dynamic calls) between the entities that enable to fullfill the search features. For each call, identify the objects that are used (C/R/U/D)

2.3) for each features, produce a mermaid class diagram representings the entities, a mermaid sequence diagram for the dynamics call, and the C/R/U/D status on used objects

2.4) Generate a slick, professional, HTML report with the informations above:
- an executive summary about the report
- the list of features and associated diagrams and informations
- a list of recommendation (quality, cybersecurity) about the implementation of the features

Overall it is HIGHLY IMPORTANT to have a PROFESSIONAL LOOKING REPORT.


---
Prompt reformulation request before launching the execution: see [analysis-prompt.ai-augmented.md](https://github.com/spashx/abyss/blob/main/examples/ILSpy%20-%20search%20feature%20analysis/analysis-prompt.ai-augmented.md)
```
To Sonnet 4.6: Create a detailled plan with tasks for the implementation for document #file:analysis-prompt.original.md.
Reformulate the requirements document with EARS notation, to have a precise, non ambiguous implementation plan in order to get the BEST POSSIBLE RESULT with an agentic IA like you. 
Generated the result into file analysis-prompt.ai-augmented.md
```
---


