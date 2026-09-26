```tikz
\begin{tikzpicture}
  \node[circle, draw, minimum size=4mm] (q0) {};
  \node[rectangle, draw, right=of q0] (q1) {};
  \node[state] at (2,-1) {};
  \draw[-{Stealth}] (q0) -- (q1);
  \node at ($(q0)!0.5!(q1)$) {};
  \begin{scope}[mindmap, concept color=black!10]
    \node[concept] {A} child {node[concept] {B}};
  \end{scope}
\end{tikzpicture}
```
