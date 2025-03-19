from fabric import Fabricator

volume_service = Fabricator(
    interval=50,
    poll_from="pactl get-sink-volume 181",
    on_changed=lambda f, v: print(f"Size of Documents: {v}"),
)

documents_fabricator = Fabricator(
    interval=1000,  # 1 second
    poll_from="du -sh /home/aman/Documents/",  # NOTE: edit this
    on_changed=lambda f, v: print(f"Size of Documents: {v.split()[0]}"),
)

# fabricator = Fabricator(
#     poll_from=lambda: "hello there!",
#     interval=1000,
# ).build(
#     lambda self, builder: builder\
#         .connect("changed", lambda *_: print("changed"))\
#         .connect("notify::value", lambda *_: print("value notified"))\
#         .set_value("initial value")
# )

volume_service.connect("changed", lambda *_: print("value notified"))