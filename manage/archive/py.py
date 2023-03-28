#!/usr/bin/env python

from flask_script import Manager, Server

from visual import create_app
from manage import *


if __name__ == "__main__":

    app = create_app('config.local.py')
    manager = Manager(app)

    manager.add_command('models-export', TourModelsExport())
    manager.add_command('models-import', TourModelsImport())
    manager.add_command('prod-data', ProductionData())
    manager.add_command('import-virtual', ImportVirtual())
    manager.add_command('novus-ordo-secolorum', NovusOrdoSecolorum())
    manager.add_command('init-partners', InitPartners())
    manager.add_command('estates-preview-resize', EstatePreviewResize())
    manager.add_command('save-sessions-to-db', SaveSessions())
    manager.add_command('stat-import-nginx-logs', StatImportNginxLogs())
    manager.add_command('rotate-quaternion-start', RotateQuaternionStart())
    manager.add_command('refactor2', Refactor2())
    manager.add_command('stat-parse-user-agents', StatParseUserAgents())
