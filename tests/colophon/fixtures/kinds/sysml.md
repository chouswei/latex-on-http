```tikz
% Reference caller body for templateId sysml. The worker owns the preamble.
% y grows downward. The port square is 3.2 mm, centred on the part edge.
% The connector stops on the outer face, 1.6 mm outside the port centre.
\begin{sysmlfigure}[view={zh-TW}, revision={label}, overrides={none}, depth={1}, body size={10}]
\begin{sysmlcanvas}
\sysmlpart{PdMon.pump}{8}{8}{18}{18}
\sysmllabel[keyword]{17}{10}{\sysmlguillemets{part}}
\sysmllabel[name]{17}{14.8}{幫浦}
\sysmllabel[type]{17}{19.7}{Pump}
\sysmlport{PdMon.pump.outlet}{26}{17}{EAST}{29.6}{11.8}{出口}{out}
\sysmlpart{PdMon.motor}{58}{8}{18}{18}
\sysmllabel[keyword]{67}{10}{\sysmlguillemets{part}}
\sysmllabel[name]{67}{14.8}{馬達}
\sysmllabel[type]{67}{19.7}{Motor}
\sysmlport{PdMon.motor.inlet}{58}{17}{WEST}{47.4}{11.8}{入口}{in}
\sysmlconnection[from=PdMon.pump.outlet, to=PdMon.motor.inlet]{PdMon.link}{(27.6,17) -- (56.4,17)}
\sysmlport{PdMon.motor.outlet}{76}{17}{EAST}{79}{11.8}{出口}{out}
\sysmlpart{PdMon.ctrl}{110}{8}{22}{18}
\sysmllabel[keyword]{121}{10}{\sysmlguillemets{part}}
\sysmllabel[name]{121}{14.8}{控制器}
\sysmllabel[type]{121}{19.7}{Controller}
\sysmlport{PdMon.ctrl.inlet}{110}{17}{WEST}{98}{11.8}{入口}{in}
\sysmlflow[from=PdMon.motor.outlet, to=PdMon.ctrl.inlet, item=液位]{PdMon.flow}{(77.6,17) -- (108.4,17)}
\sysmlport{PdMon.pump.bind}{17}{26}{SOUTH}{4}{29}{參數}{inout}
\sysmlport{PdMon.motor.bind}{67}{26}{SOUTH}{78}{29}{參數}{inout}
\sysmlbinding[from=PdMon.pump.bind, to=PdMon.motor.bind]{PdMon.bind}{(17,27.6) -- (17,36) -- (67,36) -- (67,27.6)}
\end{sysmlcanvas}
\end{sysmlfigure}
```
