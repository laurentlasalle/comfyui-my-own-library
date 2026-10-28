"""
ComfyUI - My Own Library

A personal library for your ComfyUI creations. It lists everything in the
output folder, lets you copy the creations you want to keep into a separate
library folder, and organize them with titles, a category, tags and notes.

This package adds no nodes. It only registers a few HTTP routes and a web
extension (the library window). It deliberately imports nothing heavy so it
adds no measurable time to ComfyUI's startup.
"""

from .routes import setup_routes

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "./web"

setup_routes()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
