"""
/****************************************************************************************
Copyright:  (C) Ben Wirf
Date:       April 2021
Email:      ben.wirf@gmail.com
****************************************************************************************/
"""
import os

import processing

from qgis.core import (QgsProject, QgsCoordinateTransform, QgsRectangle,
QgsTextAnnotation, QgsFillSymbol, QgsGeometry, QgsTask, QgsRasterBlockFeedback,
QgsRasterPipe, QgsRasterFileWriter, QgsRasterLayer, QgsApplication,
QgsMapLayerProxyModel, QgsWkbTypes, QgsMessageLog, QgsRasterProjector,
QgsCoordinateReferenceSystem, Qgis)

from qgis.gui import (QgsRubberBand, QgsMapToolEmitPoint, QgsMapLayerComboBox,
QgsProjectionSelectionWidget)

from PyQt5.QtCore import Qt, QPointF, QSizeF, pyqtSignal

from PyQt5.QtGui import QColor, QTextDocument, QCursor, QIcon

from PyQt5.QtWidgets import (QDockWidget, QWidget, QDialog, QHBoxLayout, QLabel, QLineEdit, QToolBar,
QAction, QMenu, QSpinBox, QPushButton, QProgressBar, QMessageBox,
QFileDialog, QGridLayout, QCheckBox)

class Basemap2Geopackage:
    
    def __init__(self, iface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.dlg = setAOIGrid()
        self.toolbar = self.iface.pluginToolBar()
        self.folder_name = os.path.dirname(os.path.abspath(__file__))
        self.icon_path = os.path.join(self.folder_name, 'icon.png')
        self.launch_action = QAction(QIcon(self.icon_path), 'Basemap2gpkg', self.iface.mainWindow())
        self.msg = QMessageBox()
        #####23-07-2021
        self.project = QgsProject().instance()
        self.project_crs = self.project.crs()
        #####
        self.coverage_layer = None
        self.grid_rubber_bands = []
        self.grid_annotations = []
        self.layer_extent_dialog = None
        self.map_tool = None
        self.rect = None
        self.log = QgsMessageLog()
        #####
        # Keep track of signal/slot connections
        self.slot1 = 'Not connected'# layer added to project
        self.slot2 = 'Not connected'# layer removed from project
        
    def initGui(self):
        self.extent_inputs = [c for c in self.dlg.widget.findChildren(QLineEdit)]
        self.grid_inputs = [b for b in self.dlg.widget.findChildren(QSpinBox)]
        for j in self.grid_inputs:
            j.valueChanged.connect(self.draw_visuals)
        self.launch_action.setObjectName('btnBM2GPKG')
        self.launch_action.triggered.connect(self.plugin_launched)
        self.toolbar.addAction(self.launch_action)
        #####02-08-21
        self.manage_action_settings()
        if self.project:
            self.project.layersAdded.connect(self.manage_action_settings)
            self.slot1 = 'Connected'
            self.project.layersRemoved.connect(self.manage_action_settings)
            self.slot2 = 'Connected'
        #####24-05-21
        self.iface.projectRead.connect(self.new_project_opened)
        self.iface.newProjectCreated.connect(self.new_project_opened)
        #####
        self.dlg.main_action.triggered.connect(self.draw_visuals)
        self.dlg.action2.triggered.connect(self.show_map_layer_dialog)
        self.dlg.action3.triggered.connect(self.reset_from_canvas_extent)
        self.dlg.res_btn.clicked.connect(self.customise_grid)
        self.dlg.dwnld_btn.clicked.connect(self.run_save_task)
        self.dlg.was_closed.connect(self.dockwidget_closed)
        self.iface.projectMenu().aboutToShow.connect(self.project_menu_opened)
    
    def new_project_opened(self):
        self.manage_action_settings()
        if self.slot1 == 'Connected':
            self.project.layersAdded.disconnect(self.manage_action_settings)
            self.slot1 = 'Not connected'
        if self.slot2 == 'Connected':
            self.project.layersRemoved.disconnect(self.manage_action_settings)
            self.slot2 = 'Not connected'
            
        self.project = QgsProject.instance()
        
        if self.slot1 == 'Not connected':
            self.project.layersAdded.connect(self.manage_action_settings)
            self.slot1 = 'Connected'
        if self.slot2 == 'Not connected':
            self.project.layersRemoved.connect(self.manage_action_settings)
            self.slot2 = 'Connected'

    def project_read(self):
        self.manage_action_settings()
            
    def project_menu_opened(self):
        if self.slot1 == 'Connected':
            self.project.layersAdded.disconnect(self.manage_action_settings)
            self.slot1 = 'Not connected'
        if self.slot2 == 'Connected':
            self.project.layersRemoved.disconnect(self.manage_action_settings)
            self.slot2 = 'Not connected'
#        self.project = None
        if self.dlg.isVisible():
            self.dlg.close()
            
    #######################02-08-2021##########################
    def manage_action_settings(self):
        if not self.dlg.isVisible():
            wms_layers = [l for l in QgsProject.instance().mapLayers().values() if l.providerType() == 'wms']
            if not wms_layers:
                if self.launch_action.isEnabled():
                    self.launch_action.setEnabled(False)
                self.launch_action.setToolTip('Add a wms layer to enable')
            else:
                if not self.launch_action.isEnabled():
                    self.launch_action.setEnabled(True)
                self.launch_action.setToolTip('Save basemap to custom tiles in geopackage')
                
    #######################02-08-2021#########################
        
    def plugin_launched(self):
        self.iface.mainWindow().addDockWidget(Qt.TopDockWidgetArea, self.dlg)
        self.dlg.setAllowedAreas(Qt.TopDockWidgetArea)
        self.dlg.sb_num_tile_rows.setValue(2)
        self.dlg.sb_num_tile_cols.setValue(2)
        self.dlg.show()
        if self.launch_action.isEnabled():
            self.launch_action.setEnabled(False)
        self.project = QgsProject.instance()
        self.project_crs = self.project.crs()
#        self.draw_visuals()
        #MOVED THE LINES BELOW TO initGui() method
#        for j in self.grid_inputs:
#            j.valueChanged.connect(self.draw_visuals)
        self.get_canvas_extent()
        self.iface.mapCanvas().zoomByFactor(1.05)
        ###23-05-21###
        self.project.crsChanged.connect(self.project_crs_changed)

    def customise_grid(self):
        self.map_tool = mapToolCustomise(self.canvas, self)
        self.canvas.setMapTool(self.map_tool)
    
    def get_canvas_extent(self):
        self.dlg.le_left.setText(str(round(self.canvas.extent().xMinimum(), 5)))
        self.dlg.le_bottom.setText(str(round(self.canvas.extent().yMinimum(), 5)))
        self.dlg.le_right.setText(str(round(self.canvas.extent().xMaximum(), 5)))
        self.dlg.le_top.setText(str(round(self.canvas.extent().yMaximum(), 5)))
        self.rect = self.canvas.extent()
        self.draw_visuals()#Added in refactor 18/05/21
#        print(self.rect)

    def reset_from_canvas_extent(self):
        self.get_canvas_extent()
        self.canvas.zoomByFactor(1.05)
        
    def show_map_layer_dialog(self):
        self.layer_extent_dialog = mapLayerDialog(self)
        self.layer_extent_dialog.show()
        
    def get_layer_extent(self):
        if self.coverage_layer is not None:
            #transform layer extent to project crs
            rec = self.coverage_layer.extent()
            src = self.coverage_layer.crs()
            tgt = self.project.crs()
            lyr_ext = self.transform_rect(rec, src, tgt)
            w = int(lyr_ext.width())
            h = int(lyr_ext.height())
            f = ((w+h)/2)*0.02
            lyr_ext.grow(f)
            self.dlg.le_left.setText(str(round(lyr_ext.xMinimum(), 5)))
            self.dlg.le_bottom.setText(str(round(lyr_ext.yMinimum(), 5)))
            self.dlg.le_right.setText(str(round(lyr_ext.xMaximum(), 5)))
            self.dlg.le_top.setText(str(round(lyr_ext.yMaximum(), 5)))
            self.rect = lyr_ext
            self.draw_visuals()#Added in refactor 18/05/21
            
    def set_grid_to_layer_extent(self):
#        print(self.rect())
        self.get_layer_extent()
        self.canvas.setExtent(self.rect)
        self.canvas.zoomByFactor(1.05)
            
    def transform_rect(self, rect, src_crs, target_crs):
        '''Helper function to transform a map layer extent to the project CRS'''
        xforma = QgsCoordinateTransform(src_crs, target_crs, QgsProject.instance())
        transformed_rect = xforma.transform(rect)
#        print('Transformed_rect: {}'.format(transformed_rect))
        return transformed_rect
        
    ############################23-05-21##############################
    def project_crs_changed(self):
        old_crs = self.project_crs # previous initialized instance attribute
#        print('Old Crs: {}'.format(old_crs))
        new_crs = self.project.crs() # get current project crs
#        print('New Crs: {}'.format(new_crs))
        xformb = QgsCoordinateTransform(old_crs, new_crs, self.project)
        if self.grid_rubber_bands is not None:
            for rb in self.grid_rubber_bands:
                geom = rb[0].asGeometry()
                rb[0].reset()
                geom.transform(xformb)
                rb[0].setToGeometry(geom)
            self.draw_from_stored_lists()
        transformed_extent = xformb.transform(self.rect)
#        print(transformed_extent)
        self.dlg.le_left.setText(str(round(transformed_extent.xMinimum(), 5)))
        self.dlg.le_bottom.setText(str(round(transformed_extent.yMinimum(), 5)))
        self.dlg.le_right.setText(str(round(transformed_extent.xMaximum(), 5)))
        self.dlg.le_top.setText(str(round(transformed_extent.yMaximum(), 5)))
        self.rect = transformed_extent
        self.project_crs = new_crs #reset crs instance attribute
    ##################################################################
                
    def draw_visuals(self):
#        print('draw_visuals_called')
#        print(self.grid_rubber_bands)
        self.clear_annotations()
        sides = [i for i in self.extent_inputs]
        self.clear_annotations()
        self.rect = QgsRectangle(float(sides[0].text()),
                                float(sides[1].text()),
                                float(sides[2].text()),
                                float(sides[3].text()))
        if self.rect is not None:
            self.draw_tile_grid()
        if self.grid_rubber_bands:
            self.draw_from_stored_lists()
        
        self.dlg.prog_lbl.setText('0/{}'.format(str(len(self.grid_rubber_bands))))
        
    def draw_from_stored_lists(self):
        '''
        show rubber bands stored in self.grid_rubber_bands nested list
        create annotations for the pixels size value stored at index 1 (2nd item) of each sublist
        '''
        self.clear_annotations()
        for rb in self.grid_rubber_bands:
            rb[0].show()
            annot = self.resolution_annotation(rb)
            self.grid_annotations.append(annot)
        for a in self.grid_annotations:
            self.project.annotationManager().addAnnotation(a)
    
    def resolution_annotation(self, rb):
        a = QgsTextAnnotation()
        a.setDocument(QTextDocument('{}m'.format(str(rb[1]))))
        a.setMarkerSymbol(None)
        sym = QgsFillSymbol()
        sym_lyr = sym.symbolLayer(0)
        sym_lyr.setFillColor(QColor('Light Grey'))
        sym_lyr.setStrokeColor(QColor('Black'))
        a.setFillSymbol(sym)
        a.setFrameOffsetFromReferencePointMm(QPointF(-5, -5))
        if len(str(rb[1])) == 2:
            a.setFrameSizeMm(QSizeF(12, 8))
        elif len(str(rb[1])) == 1:
            a.setFrameSizeMm(QSizeF(9, 8))
        a.setMapPosition(rb[0].asGeometry().boundingBox().center())
        return a
    
    def draw_tile_grid(self):
        self.clear_grid()
        tile_rows = self.dlg.sb_num_tile_rows.value()
        tile_cols = self.dlg.sb_num_tile_cols.value()
        tile_width = self.rect.width()/tile_cols
        tile_height = self.rect.height()/tile_rows
    ####30-04
        left = self.rect.xMinimum()
        bottom = self.rect.yMinimum()
        ##Create grid rbs
        for r in range(tile_rows):
            self.create_row(left, bottom, tile_cols, tile_width, tile_height)
            bottom+=tile_height
#            print(bottom)
        
    ####30-04
    def make_rect(self, left, bottom, width, height):
        right = left+width
        top = bottom+height
        rect = QgsRectangle(left, bottom, right, top)
        rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        rb.setStrokeColor(QColor('Black'))
        rb.setWidth(1)
        rb.setToGeometry(QgsGeometry().fromRect(rect))
        return rb

    def create_row(self, left, bottom, cols, width, height):
        for c in range(cols):
            self.grid_rubber_bands.append([self.make_rect(left, bottom, width, height), 5])##The (hardcoded) 5 is the problem!
            left+=width
            
    def clear_grid(self):
    ####30-04
        if self.grid_rubber_bands:
            for rb in self.grid_rubber_bands:
                if rb[0] is not None:
                    rb[0].reset()
            self.grid_rubber_bands.clear()
        self.clear_annotations()

    def clear_annotations(self):
        if self.grid_annotations:
            for a in self.grid_annotations:
                self.project.annotationManager().removeAnnotation(a)
            self.canvas.refresh()
            self.grid_annotations.clear()
    #        print(self.project.annotationManager().annotations())
        
    #----------------Create task---------------------------------------#
        
    def run_save_task(self):
#        names = ['Bing VirtualEarth', 'Esri Satellite', 'Google Satellite']
        source = self.iface.activeLayer()
#        print(source)
        if not source:
            self.msg.setText('Please select a wms/wmts basemap')
            self.msg.show()
            return
        if source is not None:
            if source.providerType() != 'wms':
                self.msg.setText('Please select a wms/wmts basemap')
                self.msg.show()
                return
        self.save_dlg = SaveDialog(self)
        res = self.save_dlg.exec_()
        if res == 1:
            file_path = self.save_dlg.le_save_path.text()
            target_crs = self.save_dlg.sel_prj.crs()
            if self.save_dlg.cb_overviews.checkState() == 2:
                overview_flag = True
            elif self.save_dlg.cb_overviews.checkState() == 0:
                overview_flag = False
            #Create task
            self.task = saveRasters('Save Raster Tiles to Geopackage',
                                    self.project,
                                    self.grid_rubber_bands,
                                    source,
                                    file_path,
                                    target_crs,
                                    overview_flag)
            self.task.progressChanged.connect(lambda: self.dlg.prog.setValue(self.task.progress()))
            self.task.currentChanged.connect(self.current_changed)
            self.task.done.connect(self.task_done)
            QgsApplication.taskManager().addTask(self.task)
    
    def current_changed(self, lbl_txt):
        self.dlg.prog_lbl.setText(lbl_txt)
    
    def task_done(self, result):
        self.dlg.prog.setValue(0)
        self.dlg.prog_lbl.setText('0/{}'.format(str(len(self.grid_rubber_bands))))
        if result == False:
            self.log.logMessage('Something went wrong...')
        else:
            self.log.logMessage('Geopackage created successfully', level=Qgis.Info)
  
    
    def dockwidget_closed(self):
        ####30-04
        self.clear_grid()
        self.clear_annotations()
        self.rect = None
        if len(self.project.annotationManager().annotations()) > 0:
            self.clear_annotations()
        if self.canvas.mapTool() == self.map_tool:
            self.iface.actionPan().trigger()
        ###02-08-21###
        wms_layers = [l for l in QgsProject.instance().mapLayers().values() if l.providerType() == 'wms']
        if wms_layers:
            self.launch_action.setEnabled(True)
        else:
            self.launch_action.setToolTip('Add a wms layer to enable')
        ###23-05-21###
        self.project.crsChanged.disconnect(self.project_crs_changed)

    def unload(self):
        self.toolbar.removeAction(self.launch_action)
        del self.launch_action
            
    #--------------------------------------------------------------------------#
class setAOIGrid(QDockWidget):
    was_closed = pyqtSignal()
    def __init__(self):
        QDockWidget.__init__(self)
        self.widget = QWidget(self)
        self.layout = QHBoxLayout(self)
        #Extent_inputs
        self.lbl_left = QLabel('X Min:', self.widget)
        self.le_left = QLineEdit(self.widget)
        self.lbl_bott = QLabel('Y Min:', self.widget)
        self.le_bottom = QLineEdit(self.widget)
        self.lbl_right = QLabel('X Max:', self.widget)
        self.le_right = QLineEdit(self.widget)
        self.lbl_top = QLabel('Y Max:', self.widget)
        self.le_top = QLineEdit(self.widget)
        #Extent Menu
        self.toolbar = QToolBar(self.widget)
        self.folder_name = os.path.dirname(os.path.abspath(__file__))
        self.icon_path = os.path.join(self.folder_name, 'reload_icon.png')
        self.main_action = QAction(QIcon(self.icon_path), 'Set extent options', self.toolbar)
        self.extent_menu = QMenu(self.toolbar)
#        self.action1 = QAction('Reset grid extent from manual inputs', self.toolbar)
        self.action2 = QAction('Set grid extent from layer', self.toolbar)
        self.action3 = QAction('Reset grid extent from current canvas extent', self.toolbar)
#        self.extent_menu.addAction(self.action1)
        self.extent_menu.addAction(self.action2)
        self.extent_menu.addAction(self.action3)
        self.main_action.setMenu(self.extent_menu)
        self.toolbar.addAction(self.main_action)
        #Grid_inputs
        self.lbl_tile_rows = QLabel('Tile rows:', self.widget)
        self.sb_num_tile_rows = QSpinBox(self.widget)
        self.sb_num_tile_rows.setMinimum(1)
        self.sb_num_tile_rows.setValue(2)
        self.lbl_tile_cols = QLabel('Tile cols:', self.widget)
        self.sb_num_tile_cols = QSpinBox(self.widget)
        self.sb_num_tile_cols.setMinimum(1)
        self.sb_num_tile_cols.setValue(2)
        self.res_btn = QPushButton('Customize', self.widget)
        self.dwnld_btn = QPushButton('Download', self.widget)
        self.prog_lbl = QLabel('0/4', self.widget)
        self.prog = QProgressBar(self.widget)
        for w in self.widget.children():
            self.layout.addWidget(w)
        self.widget.setLayout(self.layout)
        self.setWidget(self.widget)
        
    def closeEvent(self, e):
        self.was_closed.emit()

###---------------------Task Save Rasters Class-----------------------------###
class saveRasters(QgsTask):
    currentChanged = pyqtSignal(str)
    done = pyqtSignal(bool)
    def __init__(self, desc, project, grid, source, save_path, crs, build_overviews):
        QgsTask.__init__(self, desc)
        self.project = project
        self.grid = grid
        self.source = source
        self.save_path = save_path
        self.crs = crs
        self.build_overviews = build_overviews
        self.feedback = QgsRasterBlockFeedback()
        self.feedback.progressChanged.connect(lambda: self.setProgress(self.feedback.progress()))
        self.xform1 = QgsCoordinateTransform(self.project.crs(), self.source.crs(), self.project)
        self.xform2 = QgsCoordinateTransform(self.project.crs(), self.crs, self.project)
        
    def run(self):
        provider = self.source.dataProvider()
        pipe = QgsRasterPipe()
        pipe.set(provider.clone())
        if self.source.crs() != self.crs:
            projector = QgsRasterProjector()
            projector.setCrs(self.source.crs(), self.crs, self.project.transformContext())
            pipe.insert(2, projector)
        for current, rb in enumerate(self.grid):
            self.currentChanged.emit('{}/{}'.format(str(current+1), str(len(self.grid))))
            #get extent of each grid rb and write to gpkg
            tile_rect = rb[0].asGeometry().boundingBox()
            pixel_size = rb[1]
            ###################################################
            cols = int(tile_rect.width()/pixel_size)
            rows = int(tile_rect.height()/pixel_size)
            if self.project.crs() != 'EPSG:3857':
                extent_m = self.xform1.transform(tile_rect)
                cols = int(extent_m.width()/pixel_size)
                rows = int(extent_m.height()/pixel_size)
            if self.project.crs() != self.crs:
                tile_rect = self.xform2.transform(tile_rect)
            #######################################
            fw = QgsRasterFileWriter(self.save_path)
            fw.setOutputFormat('gpkg')
            tbl_name = 'image_tile{}'.format(str(current+1))
            tbl = 'RASTER_TABLE={}'.format(tbl_name)
            fw.setCreateOptions([tbl, 'APPEND_SUBDATASET=YES'])
            err = fw.writeRaster(pipe,
                                cols,
                                rows,
                                tile_rect,
                                self.crs,
                                feedback = self.feedback)
                                
            #TODO: Make sure path matches save file path!
            if self.build_overviews:
                if err == 0:
                    path = 'GPKG:{}:image_tile{}'.format(self.save_path, current+1)
                    input = QgsRasterLayer(path, 'tile', 'gdal')
                    params = {'INPUT':input,
                        'CLEAN':False,
                        'LEVELS':'2 4 8 16',
                        'RESAMPLING':1,
                        'FORMAT':0,
                        'EXTRA':''}
                    processing.run("gdal:overviews", params)
            del fw
        return True
        
    def finished(self, result):
        self.done.emit(result)
        
###------------------------------------------------------------------------###

class mapLayerDialog(QDialog):
    '''Class to provide a Dialog to select a map layer by which to set
    the grid extent'''
    def __init__(self, parent):
        QDialog.__init__(self)
        self.parent = parent
        self.setGeometry(750, 300, 325, 150)
        self.setWindowTitle('Set Extent From Map Layer')
        self.lbl = QLabel('Select layer: ', self)
        self.lyr_cb = QgsMapLayerComboBox(self)
        self.lyr_cb.setFilters(QgsMapLayerProxyModel.RasterLayer | QgsMapLayerProxyModel.HasGeometry)
        self.ok_btn = QPushButton('Set Grid Extent', self)
        self.layout = QGridLayout()
        self.layout.addWidget(self.lbl, 0, 0, 1, 1, Qt.AlignCenter)#from row, from column, row span, column span
        self.layout.addWidget(self.lyr_cb, 0, 1, 1, 2)
        self.layout.addWidget(self.ok_btn, 1, 2, 1, 1)
        self.setLayout(self.layout)
        self.ok_btn.clicked.connect(self.ok)
        
    def ok(self):
        self.parent.coverage_layer = self.lyr_cb.currentLayer()
        self.parent.set_grid_to_layer_extent()
#        self.parent.draw_visuals()
        self.hide()
        
class resolutionDialog(QDialog):
    def __init__(self, parent):
        self.parent = parent
        QDialog.__init__(self)
        self.setGeometry(750, 300, 325, 150)
        self.setWindowTitle('Set tile download resolution')
        self.lbl1 = QLabel('Pixel size (meters):', self)
        self.sb = QSpinBox(self)
        self.sb.setRange(1, 99)
        self.sb.selectAll()
        self.lbl2 = QLabel('Apply to all: ', self)
        self.cb = QCheckBox(self)
        self.btn_ok = QPushButton('OK', self)
        self.btn_ok.clicked.connect(self.ok_clicked)
        self.layout = QGridLayout()
        #QWidget *widget, int fromRow, int fromColumn, int rowSpan, int columnSpan, Qt::Alignment alignment
        self.layout.addWidget(self.lbl1, 0, 0, 1, 1)
        self.layout.addWidget(self.sb, 0, 1, 1, 1)
        self.layout.addWidget(self.lbl2, 1, 0, 1, 1)
        self.layout.addWidget(self.cb, 1, 1, 1, 1)
        self.layout.addWidget(self.btn_ok, 2, 1, 1, 1)
        self.setLayout(self.layout)
        
    def ok_clicked(self):
        self.accept()

###########################Add Save Dialog##################################
class SaveDialog(QDialog):
    def __init__(self, parent):
        QDialog.__init__(self)
        self.parent = parent
        self.setGeometry(500, 250, 650, 350)
        self.lbl_save_path = QLabel('File Path:', self)
        self.le_save_path = QLineEdit(self)
        self.btn_save_path = QPushButton('...', self)
        self.btn_save_path.clicked.connect(self.get_save_path)
        self.lbl_prj = QLabel('Target CRS:', self)
        self.sel_prj = QgsProjectionSelectionWidget(self)
        self.sel_prj.setCrs(QgsProject.instance().crs())
        self.sel_prj.setOptionVisible(QgsProjectionSelectionWidget.RecentCrs, True)
        self.sel_prj.setMaximumHeight(self.btn_save_path.height())
        self.lbl_overviews = QLabel('Build Overviews ', self)
        self.cb_overviews = QCheckBox(self)
        self.cb_overviews.setCheckState(Qt.Checked)
        self.btn_accept = QPushButton('Save', self)
        self.btn_accept.clicked.connect(lambda: self.accept())
        self.btn_reject = QPushButton('Cancel', self)
        self.btn_reject.clicked.connect(lambda: self.reject())
        
        self.layout = QGridLayout(self)
        self.layout.addWidget(self.lbl_save_path, 0, 0, 1, 1, Qt.AlignCenter)
        self.layout.addWidget(self.le_save_path, 0, 1, 1, 4)
        self.layout.addWidget(self.btn_save_path, 0, 5, 1, 1)
        self.layout.addWidget(self.lbl_prj, 1, 0, 1, 1, Qt.AlignCenter)
        self.layout.addWidget(self.sel_prj, 1, 1, 1, 5)
        self.layout.addWidget(self.lbl_overviews, 2, 1, 1, 1)
        self.layout.addWidget(self.cb_overviews,2, 2, 1, 4)
        self.layout.addWidget(self.btn_accept, 2, 4, 1, 1)
        self.layout.addWidget(self.btn_reject, 2, 5, 1, 1)
        self.layout.setVerticalSpacing(65)
        self.setLayout(self.layout)
        
    def get_save_path(self):
        file_name = QFileDialog().getSaveFileName(self.parent.iface.mainWindow(), 'Save Tiles to Geopackage', '', filter='*.gpkg')
        if file_name:
            file_path = file_name[0]
            self.le_save_path.setText(file_path)


############################################################################

class mapToolCustomise(QgsMapToolEmitPoint):
    def __init__(self, canvas, parent):
        self.canvas = canvas
        self.parent = parent
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.cursor = QCursor()
        self.cursor.setShape(Qt.ArrowCursor)
        self.setCursor(self.cursor)
        self.point = None
        
    def canvasPressEvent(self, e):
        self.point = e.mapPoint()
        if QgsGeometry().fromRect(self.parent.rect).contains(e.mapPoint()):
            if e.button() == Qt.LeftButton:
                current_resolution = [rb[1] for rb in self.parent.grid_rubber_bands if rb[0].asGeometry().contains(e.mapPoint())][0]
                self.dlg = resolutionDialog(self.parent)
                self.dlg.sb.setValue(current_resolution)
                self.dlg.show()
                self.dlg.accepted.connect(self.set_resolution)
            elif e.button() == Qt.RightButton:
                for rb in self.parent.grid_rubber_bands:
                        if rb[0].asGeometry().contains(e.mapPoint()):
                            rb[0].setStrokeColor(QColor('Red'))
                            m = QMessageBox()
                            m.addButton(QPushButton('Cancel'), QMessageBox.RejectRole)
                            m.addButton(QPushButton('OK'), QMessageBox.AcceptRole)
                            m.setText('Remove grid tile?')
                            result = m.exec_()
                            if result == 1:#Removes grid cell even if 'X' button clicked!!
                                rb[0].reset()
                                self.parent.grid_rubber_bands.remove(rb)
                                self.parent.draw_from_stored_lists()
                            elif result == 0:
                                rb[0].setStrokeColor(QColor('Black'))
            
            
    def set_resolution(self):
#        print(self.point)
        res = self.dlg.sb.value()
        if self.dlg.cb.checkState() == 0:
            for rb in self.parent.grid_rubber_bands:
                if rb[0].asGeometry().contains(self.point):
                    rb[1] = res
        elif self.dlg.cb.checkState() == 2:
            for rb in self.parent.grid_rubber_bands:
                rb[1] = res
        self.parent.draw_from_stored_lists()
    


