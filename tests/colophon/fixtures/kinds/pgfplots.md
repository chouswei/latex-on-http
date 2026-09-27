```tikz
\begin{tikzpicture}
  \begin{axis}
    \addplot {x};
  \end{axis}
\end{tikzpicture}
\begin{tikzpicture}
  \begin{axis}
    % Small 3D sample. This worker does not set a numeric sample budget.
    \addplot3[samples=2, domain=0:1] ({x}, {1-x}, {x});
  \end{axis}
\end{tikzpicture}
```
