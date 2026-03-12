 python evaluate_swe_bench.py \
   --repo pallets/flask \
   --limit 3 \
   --agents 3 \
   --rounds 3 \
   --parallel 3 \
   --run-eval \
   --eval-workers 2 \
   --provider opencode \
   --model gemini-3-flash \
   --dashboard

python evaluate_swe_bench.py \
   --repo scikit-learn/scikit-learn \
   --limit 3 \
   --agents 3 \
   --rounds 3 \
   --parallel 3 \
   --run-eval \
   --eval-workers 3 \
   --provider opencode \
   --model gemini-3-flash \
   --dashboard


   
   n-eval \
   --eval-workers 2 \
   --provider opencode \
   --model gemini-3-flash

   

#,Task ID,Reasoning for High Difficulty
1,django__django-11133,Architectural Depth: Interaction between BinaryField and MemoryView. Requires fixing core serialization logic rather than surface models.
2,django__django-16527,Middleware Intersection: Admin permission bug that requires reasoning across multiple authentication and middleware layers.
3,astropy__astropy-12907,Hierarchy Depth: Deep class inheritance in a scientific codebase. Testing requires astronomical precision that simple unit tests miss.
4,scikit-learn__scikit-learn-10297,Overfitting Trap: Linear regression edge case. Most agents pass basic tests but fail the hidden statistical cross-validation.
5,sympy__sympy-16792,Recursive Math: Symbolic math bug. Requires recursive reasoning that most LLMs fail to trace correctly.
6,pytest-dev__pytest-7205,"Plugin Trap: Description omits the plugin architecture, but the fix must be plugin-compatible to pass the ""Gold"" suite."
7,matplotlib__matplotlib-23562,"Visual Guesswork: Requires the agent to ""guess"" a specific visual rendering state not explicitly described in the text."
8,pylint-dev__pylint-6528,"Psychic Requirement: Audit-confirmed ""Trap"" requiring an unmentioned function (get_annotation) to satisfy the verifier."
9,django__django-14752,Abstraction Trap: JsonResponse issue with nested objects. Models struggle to find the correct layer in the stack.
10,sphinx-doc__sphinx-8721,Complex Tree logic: Documentation rendering bug requiring understanding of Sphinx's internal node construction.
11,scikit-learn__scikit-learn-25570,"API Strictness: Transformer/pipeline mismatch. A ""Type-Mismatch"" nightmare requiring perfect adherence to internal APIs."
12,sympy__sympy-13437,Complex Substitution: A SymPy bug involving limit calculations and nested expressions that breaks standard simplification paths.
13,django__django-11583,State Size: Migration auto-detection bug. Involves massive state objects that challenge model context windows.
14,pytest-dev__pytest-11148,"Backward Compatibility: Refactor of the Config object. Agents ""fix"" the bug but break the existing P2P test suite."
15,scikit-learn__scikit-learn-12471,"Pipeline Logic: One-hot encoding edge cases. Requires handling ""unseen categories"" consistently across an entire workflow."
16,django__django-13658,"Underspecified: Requirement regarding ManagementUtility. Solve the bug but fail on ""hidden"" implementation checks."
17,sympy__sympy-13878,Numerical Precision: Interaction between SymPy's N() function and specific trigonometric simplifications.
18,matplotlib__matplotlib-23964,"Visual Regression: Hard to verify logically; requires agents to ""reason"" about backend rendering states."
19,django__django-12482,Isolation Level: Async DB bug manifesting only under specific transaction-isolation levels. Very hard to deduce.
20,sphinx-doc__sphinx-8506,Inheritance Maze: Involves autodoc extensions. Models often fail to localize the bug within the massive codebase.
21,astropy__astropy-13033,Time-Series Parsing: Obscure bug in how metadata is preserved during specific time-series joins.
22,django__django-16046,Engine Logic: Bug in the QuerySet engine. Requires understanding the SQL-generation layer of the ORM.
23,scikit-learn__scikit-learn-11040,Nested Logic: Requires changes to how GridSearchCV handles nested dictionaries. High risk of logical regression.
24,sympy__sympy-14396,Poly-Algorithm Failure: Obscure bug in polynomial division that requires specialized mathematical verification.
25,pytest-dev__pytest-7432,Async State: Internal object state bug during parallel execution. Tests ability to reason about shared memory/concurrency.
26,django__django-15347,Event Loop Logic: Involves AsyncClient and session management. Models often miss the subtle async/sync boundary.
27,requests__requests-3362,Connection Pooling: Connection-pooling bug in urllib3. Requires understanding internal states under heavy load.
28,django__django-14855,Remote URL Handling: Complex interaction between get_admin_url and custom admin sites.
29,sympy__sympy-22914,Series Expansion: Bug in the limit logic for series containing factorials—frequently leads to infinite loops in weak agents.
30,marshmallow-code__marshmallow-602,High Scope: Deep refactor of schema validation logic. Requires changing 15+ functions simultaneously.					

python evaluate_swe_bench.py \
   --task-ids django__django-11133,django__django-13768,django__django-14752 \
   --agents 3 \
   --rounds 3 \
   --parallel 3 \
   --run-eval \
   --eval-workers 3 \
   --provider opencode \
   --model gemini-3-flash \
   --dashboard


python evaluate_swe_bench.py \
   --task-ids django__django-11133,django__django-16527,astropy__astropy-12907,scikit-learn__scikit-learn-10297,sympy__sympy-16792,pytest-dev__pytest-7205,matplotlib__matplotlib-23562,pylint-dev__pylint-6528,django__django-14752,sphinx-doc__sphinx-8721,scikit-learn__scikit-learn-25570,sympy__sympy-13437,django__django-11583,pytest-dev__pytest-11148,scikit-learn__scikit-learn-12471,django__django-13658,sympy__sympy-13878,matplotlib__matplotlib-23964,django__django-12482,sphinx-doc__sphinx-8506,astropy__astropy-13033,django__django-16046,scikit-learn__scikit-learn-11040,sympy__sympy-14396,pytest-dev__pytest-7432,django__django-15347,requests__requests-3362,django__django-14855,sympy__sympy-22914,marshmallow-code__marshmallow-602 \
   --agents 3 \
   --rounds 3 \
   --parallel 3 \
   --run-eval \
   --eval-workers 3 \
   --provider opencode \
   --model gemini-3-flash \
   --dashboard


python3 evaluate_swe_bench.py \
   --task-ids "django__django-16263,django__django-13513,astropy__astropy-13033,django__django-15098,django__django-13195,django__django-13512,sphinx-doc__sphinx-9461,sphinx-doc__sphinx-9229,django__django-13794,django__django-14170" \
   --agents 3 \
   --rounds 3 \
   --parallel 3 \
   --run-eval \
   --eval-workers 3 \
   --provider opencode \
   --model gemini-3-flash \
   --dashboard

python evaluate_swe_bench.py \
    --repo pallets/flask \
    --limit 3 \
    --agents 5 \
    --rounds 3 \
    --parallel 3 \
    --run-eval \
    --eval-workers 2 \
    --provider opencode \
    --model "gemini-3-pro,claude-sonnet-4.5,gpt-5.4-pro,minimax-m2.1,qwen3-coder" \
    --dashboard
