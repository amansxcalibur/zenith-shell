from i3ipc import Connection, Event

i3 = Connection()
count = 0
for con in i3.get_workspaces():
    print(con.name)
    count+=1
print("her eis the count ",count)
# def on_workspace_focus(self, e):
#     if e.current:
#         print("Window in workspacez")
#         print(e.current.num)
#         # for w in e.current.leaves():
#         #     print(w.num)
# i3.on(Event.WORKSPACE_FOCUS, on_workspace_focus)
# i3.main()