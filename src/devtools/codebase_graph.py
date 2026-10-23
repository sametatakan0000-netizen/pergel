"""Graphify & code-review-graph birleşimi yerel AST Kod Tabanı Bilgi Grafiği Motoru."""
import ast
import json
import os
from typing import Any, Dict, List, Set


def build_codebase_knowledge_graph(
    src_root: str, output_json_path: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "CODEBASE_GRAPH.json")
) -> Dict[str, Any]:
    """Modülleri, sınıfları, fonksiyonları, çağrı ağını, ölü kod adaylarını ve risk puanını çıkarır."""
    modules: List[Dict[str, Any]] = []
    defined_functions: Dict[str, str] = {}
    all_called_names: Set[str] = set()

    abs_root = os.path.abspath(src_root)
    parent_root = os.path.dirname(abs_root)

    for dirpath, dirnames, filenames in os.walk(abs_root):
        dirnames[:] = [d for d in sorted(dirnames) if d not in {"__pycache__", ".git"}]
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(fpath, parent_root)
            mod_name = rel_path[:-3].replace(os.sep, ".")
            if mod_name.endswith(".__init__"):
                mod_name = mod_name[: -len(".__init__")]

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source, filename=fpath)
            except Exception:
                continue

            classes: List[str] = []
            functions: List[str] = []
            imports: List[str] = []
            calls: Set[str] = set()
            branch_nodes = 0

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
                    if not node.name.startswith("_"):
                        defined_functions[f"{mod_name}.{node.name}"] = node.name
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        calls.add(node.func.id)
                        all_called_names.add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        calls.add(node.func.attr)
                        all_called_names.add(node.func.attr)
                elif isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                    branch_nodes += 1

            loc = len(source.splitlines())
            risk_score = round(
                min(10.0, (loc / 80.0) + (branch_nodes * 0.4) + (len(imports) * 0.2)), 2
            )

            modules.append(
                {
                    "module": mod_name,
                    "path": rel_path,
                    "loc": loc,
                    "classes": classes,
                    "functions": functions,
                    "imports": sorted(set(imports)),
                    "calls": sorted(calls),
                    "change_risk": risk_score,
                }
            )

    dead_code_candidates = [
        qual_name
        for qual_name, short_name in sorted(defined_functions.items())
        if short_name not in all_called_names and not short_name.startswith("test_")
    ]

    graph_data = {
        "summary": {
            "total_files": len(modules),
            "total_classes": sum(len(m["classes"]) for m in modules),
            "total_functions": sum(len(m["functions"]) for m in modules),
            "total_loc": sum(m["loc"] for m in modules),
        },
        "modules": modules,
        "dead_code_candidates": dead_code_candidates,
    }

    if output_json_path:
        try:
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    return graph_data
