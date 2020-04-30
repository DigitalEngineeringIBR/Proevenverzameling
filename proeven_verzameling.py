# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ProevenVerzameling
                                 A QGIS plugin
 Queries chosen features to a database
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2019-10-20
        git sha              : $Format:%H$
        copyright            : (C) 2019 by Kevin Schuurman
        email                : k.schuurman1@rotterdam.nl
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import sys
import os
import traceback
import pandas as pd
import numpy as np
import xlsxwriter
import cx_Oracle

from qgis.core import QgsDataSourceUri, QgsCredentials, Qgis, QgsTask, QgsApplication
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QRegExp
from qgis.PyQt.QtGui import QIcon, QRegExpValidator
from qgis.PyQt.QtWidgets import QAction, QDialogButtonBox, QProgressDialog

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .proeven_verzameling_dialog import ProevenVerzamelingDialog
from . import qgis_backend


class ProevenVerzameling:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'ProevenVerzameling_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Proeven Verzameling')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('ProevenVerzameling', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/proeven_verzameling/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Proeven Verzameling'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Proeven Verzameling'),
                action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        """Run method that performs all the real work"""
        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start:
            self.first_start = False
            self.dlg = ProevenVerzamelingDialog()
            self.reset_ui()
            # Initialize QGIS filewidget to select a directory
            self.dlg.fileWidget.setStorageMode(1)
            # Signalling the Open button. Here the actual logic behind the plugin starts
            self.dlg.buttonBox.button(
                QDialogButtonBox.Ok).clicked.connect(self.read_form)
            # Signalling the reset button.
            self.dlg.buttonBox.button(
                QDialogButtonBox.RestoreDefaults).clicked.connect(self.reset_ui)
            rx1 = QRegExp(r"^\[\d{1,2}(\.\d{1})?(?:,\d{1,2}(\.\d{1})?)+\]$")
            vg_validator = QRegExpValidator(rx1)
            self.dlg.le_vg_sdp.setValidator(vg_validator)
            self.dlg.le_vg_trx.setValidator(vg_validator)

            rx2 = QRegExp(r"^[\w\-. ]+$")
            filename_validator = QRegExpValidator(rx2)
            self.dlg.le_outputName.setValidator(filename_validator)

        # Look for all the databases connected in Qgis
        settings = QSettings()
        allkeys = settings.allKeys()
        databases = [k for k in allkeys if 'database' in k]
        databaseNames = [settings.value(k) for k in databases]
        # Holding on to the previous current index
        cur_i = self.dlg.cmb_databases.currentIndex()
        self.dlg.cmb_databases.clear()
        self.dlg.cmb_databases.addItems(databaseNames)
        # On first_start there would be no previous current index and currentIndex would return -1
        if cur_i != -1:
            self.dlg.cmb_databases.setCurrentIndex(cur_i)

        # show the dialog
        self.dlg.show()

    def read_form(self):
        ''' Extraction of info from the dialog form.
            Checking credentials for the Oracle database connection.'''
        filter_on_height = self.dlg.cb_filterOnHeight.isChecked()
        filter_on_volumetric_weight = self.dlg.cb_filterOnVolumetricWeight.isChecked()
        selected_layer = self.dlg.cmb_layers.currentLayer()
        database = self.dlg.cmb_databases.currentText()
        trx_bool = self.dlg.cb_TriaxiaalProeven.isChecked()
        sdp_bool = self.dlg.cb_SamendrukkingProeven.isChecked()
        output_location = self.dlg.fileWidget.filePath()
        output_name = self.dlg.le_outputName.text()
        args = {'selected_layer': selected_layer,
                'output_location': output_location, 'output_name': output_name,
                }

        if trx_bool:
            ## asserts ...    


            ##

            proef_types = []
            if self.dlg.cb_CU.isChecked():
                proef_types.append('CU')
            if self.dlg.cb_CD.isChecked():
                proef_types.append('CD')
            if self.dlg.cb_UU.isChecked():
                proef_types.append('UU') 
            args['proef_types'] = proef_types
            args['ea'] = self.dlg.sb_strain.value()
            args['save_plot'] = self.dlg.cb_savePlot.isChecked()
            

            if self.dlg.le_vg_trx.text():
                volG_trx = self.dlg.le_vg_trx.text().strip('[').strip(']').split(',')
                volG_trx = [float(x) for x in volG_trx]
                if len(volG_trx) < 2:
                    volG_trx = None
            else:
                volG_trx = None
            args['volG_trx'] = volG_trx

        if sdp_bool:
            if self.dlg.le_vg_sdp.text():
                volG_sdp = self.dlg.le_vg_sdp.text().strip(
                    '[').strip(']').split(',')
                volG_sdp = [float(x) for x in volG_sdp]
                if len(volG_sdp) < 2:
                    volG_sdp = None
            else:
                volG_sdp = None
            args['volG_sdp'] = volG_sdp

        if filter_on_height:
            args['maxH'] = self.dlg.sb_maxHeight.value()
            args['minH'] = self.dlg.sb_minHeight.value()
        if filter_on_volumetric_weight:
            args['maxVg'] = self.dlg.sb_maxVolumetricWeight.value()
            args['minVg'] = self.dlg.sb_minVolumetricWeight.value()

        settings = QSettings()
        allkeys = settings.allKeys()
        allvalues = [settings.value(k) for k in allkeys]
        allsettings = dict(zip(allkeys, allvalues))
        for key, val in allsettings.items():
            if 'database' in key:
                if val == database:
                    databasekey = key
        databasekey = databasekey.rstrip('database')
        selected_databasekeys = [k for k in allkeys if databasekey in k]
        host = settings.value(
            [k for k in selected_databasekeys if 'host' in k][0])
        port = settings.value(
            [k for k in selected_databasekeys if 'port' in k][0])

        saveUsername = settings.value(
            [k for k in selected_databasekeys if 'saveUsername' in k][0], None)
        savePassword = settings.value(
            [k for k in selected_databasekeys if 'savePassword' in k][0], None)
        username = None
        password = None
        if saveUsername == 'true':
            saveUsername = True
            username = settings.value(
                [k for k in selected_databasekeys if 'username' in k][0], None)
        if savePassword == 'true':
            savePassword = True
            password = settings.value(
                [k for k in selected_databasekeys if 'password' in k][0], None)

        errorMessage = None
        if saveUsername is True and savePassword is True:
            try:
                qb = qgis_backend.qgis_backend(
                    host=host, port=port, database=database, username=username, password=password)
                qb.check_connection()
                args['qb'] = qb
                self.run_task(args)
            except cx_Oracle.DatabaseError as e:
                errorObj, = e.args
                errorMessage = errorObj.message
                suc = 'false'
                while suc == 'false':
                    suc, qb, errorMessage = self.get_credentials(
                        host, port, database, username=username, password=password, message=errorMessage)
                if suc == 'exit':
                    pass
                elif suc == 'true':
                    args['qb'] = qb
                    self.run_task(args)
        else:
            suc, qb, errorMessage = self.get_credentials(
                host, port, database, username=username, password=password)
            while suc == 'false':
                suc, qb, message = self.get_credentials(
                    host, port, database, message=errorMessage)
            if suc == 'exit':
                pass
            elif suc == 'true':
                args['qb'] = qb
                self.run_task(args)

    def run_task(self, args):
        progressDialog = QProgressDialog(
            'Initializing Task: BIS Bevraging...', 'Cancel', 0, 100)
        progressDialog.show()
        task = ProevenVerzamelingTask(
            'Proeven Verzameling Bevraging', self.iface, **args)
        task.progressChanged.connect(
            lambda: progressDialog.setValue(task.progress()))
        progressDialog.canceled.connect(task.cancel)
        task.begun.connect(lambda: progressDialog.setLabelText(
            'Task Running: BIS Bevraging...'))
        QgsApplication.taskManager().addTask(task)

    def reset_ui(self):
        '''Reset all inputs to default values in the GUI'''
        self.dlg.cb_filterOnHeight.setChecked(False)
        self.dlg.sb_maxHeight.setValue(100)
        self.dlg.sb_minHeight.setValue(-100)
        self.dlg.cb_filterOnVolumetricWeight.setChecked(False)
        self.dlg.sb_maxVolumetricWeight.setValue(22)
        self.dlg.sb_minVolumetricWeight.setValue(8)
        self.dlg.cb_TriaxiaalProeven.setChecked(False)
        self.dlg.cb_SamendrukkingProeven.setChecked(False)
        self.dlg.cb_CU.setChecked(True)
        self.dlg.cb_CD.setChecked(False)
        self.dlg.cb_UU.setChecked(False)
        self.dlg.sb_strain.setValue(5)
        self.dlg.cb_savePlot.setChecked(False)
        self.dlg.fileWidget.setFilePath(self.dlg.fileWidget.defaultRoot())
        self.dlg.le_outputName.setText('BIS_Geo_Proeven')

    def get_credentials(self, host, port, database, username=None, password=None, message=None):
        uri = QgsDataSourceUri()
        # assign this information before you query the QgsCredentials data store
        uri.setConnection(host, port, database, username, password)
        connInfo = uri.connectionInfo()

        (success, user, passwd) = QgsCredentials.instance().get(
            connInfo, username, password, message)
        qb = None
        errorMessage = None
        if success:
            try:
                qb = qgis_backend.qgis_backend(
                    host=host, port=port, database=database, username=user, password=passwd)
                qb.check_connection()
                return 'true', qb, errorMessage
            except cx_Oracle.DatabaseError as e:
                errorObj, = e.args
                errorMessage = errorObj.message
                return 'false', qb, errorMessage
        else:
            return 'exit', qb, errorMessage

    def qgis_frontend(self,
                      qb,
                      selected_layer,
                      CU, CD, UU, ea,
                      save_plot,
                      output_location, output_name,
                      maxH=1000, minH=-1000, maxVg=40, minVg=0
                      ):

        proef_types = []  # ['CU','CD','UU']
        if CU:
            proef_types.append('CU')
        if CD:
            proef_types.append('CD')
        if UU:
            proef_types.append('UU')

        rek_selectie = [ea]
        output_file = output_name + '.xls'

        # Check if the directory still has to be made.
        if os.path.isdir(output_location) is False:
            os.mkdir(output_location)

        # Extract the loc ids from the selected points in the selected layer
        loc_ids = qb.get_loc_ids(selected_layer)
        # Get all meetpunten related to these loc_ids
        df_meetp = qb.get_meetpunten(loc_ids)
        df_geod = qb.get_geo_dossiers(df_meetp.GDS_ID)
        df_gm = qb.get_geotech_monsters(loc_ids)
        if df_gm is not None:
            df_gm_filt_on_z = qb.select_on_z_coord(df_gm, maxH, minH)
            if df_gm_filt_on_z is None:
                self.iface.messageBar().pushMessage("Error", "There are no Geotechnische monsters in this depth range. {} to {} mNAP".format(
                    maxH, minH), level=Qgis.Critical, duration=5)
        # Add the df_meetp, df_geod and df_gm_filt_on_z to a dataframe dictionary
        df_dict = {'BIS_Meetpunten': df_meetp, 'BIS_GEO_Dossiers': df_geod,
                   'BIS_Geotechnische_Monsters': df_gm_filt_on_z}

        df_sdp = qb.get_sdp(df_gm_filt_on_z.GTM_ID)
        if df_sdp is not None:
            df_sdp = qb.select_on_vg(df_sdp, maxVg, minVg)
        if df_sdp is not None:
            df_sdp_result = qb.get_sdp_result(df_gm.GTM_ID)
            df_dict.update({'BIS_SDP_Proeven': df_sdp,
                            'BIS_SDP_Resultaten': df_sdp_result})

        df_trx = qb.get_trx(df_gm_filt_on_z.GTM_ID, proef_type=proef_types)
        if df_trx is not None:
            df_trx = qb.select_on_vg(df_trx, maxVg, minVg)
        if df_trx is not None:
            # Get all TRX results, TRX deelproeven and TRX deelproef results
            df_trx_results = qb.get_trx_result(df_trx.GTM_ID)
            df_trx_dlp = qb.get_trx_dlp(df_trx.GTM_ID)
            df_trx_dlp_result = qb.get_trx_dlp_result(df_trx.GTM_ID)
            df_dict.update({'BIS_TRX_Proeven': df_trx, 'BIS_TRX_Results': df_trx_results,
                            'BIS_TRX_DLP': df_trx_dlp, 'BIS_TRX_DLP_Results': df_trx_dlp_result})
            df_bbn_stat_dict = {}
            df_vg_stat_dict = {}
            df_lst_sqrs_dict = {}
            # Doing statistics on the select TRX proeven
            if len(df_trx.index) > 1:
                # Create a linear space between de maximal volumetric weight and the minimal volumetric weight
                minvg, maxvg = min(df_trx.VOLUMEGEWICHT_NAT), max(
                    df_trx.VOLUMEGEWICHT_NAT)
                N = round(len(df_trx.index)/5) + 1
                cutoff = 1  # The interval cant be lower than 1 kn/m3
                if (maxvg-minvg)/N > cutoff:
                    Vg_linspace = np.linspace(minvg, maxvg, N)
                else:
                    N = round((maxvg-minvg)/cutoff)
                    if N < 2:
                        Vg_linspace = np.linspace(minvg, maxvg, 2)
                    else:
                        Vg_linspace = np.linspace(minvg, maxvg, N)

                Vgmax = Vg_linspace[1:]
                Vgmin = Vg_linspace[0:-1]

                for ea in rek_selectie:
                    ls_list = []
                    avg_list = []
                    for vg_max, vg_min in zip(Vgmax, Vgmin):
                        # Make a selection for this volumetric weight interval
                        gtm_ids = qb.select_on_vg(
                            df_trx, Vg_max=vg_max, Vg_min=vg_min, soort='nat')['GTM_ID']
                        if len(gtm_ids) > 0:
                            # Create a tag for this particular volumetric weight interval
                            key = 'Vg: ' + str(round(vg_min, 1)) + \
                                '-' + str(round(vg_max, 1)) + ' kN/m3'
                            # Get the related TRX results...
                            #
                            # Potentially the next line could be done without querying the database again
                            # for the data that is already availabe in the variable df_trx_results
                            # but I have not found the right type of filter methods in Pandas which
                            # can replicate the SQL filters
                            #
                            df_trx_results_temp = qb.get_trx_result(gtm_ids)
                            # Calculate the averages and standard deviation of fi and coh for different strain types and add them to a dataframe list
                            mean_fi, std_fi, mean_coh, std_coh, N = qb.get_average_per_ea(
                                df_trx_results_temp, ea)
                            df_avg_temp = pd.DataFrame(index=[key], data=[[vg_min, vg_max, mean_fi, mean_coh, std_fi, std_coh, N]],
                                                       columns=['MIN(VG)', 'MAX(VG)', 'MEAN(FI)', 'MEAN(COH)', 'STD(FI)', 'STD(COH)', 'N'])
                            avg_list.append(df_avg_temp)
                            # Calculate the least squares estimate of the S en T and add them to a dataframe list
                            fi, coh, E, E_per_n, eps, N = qb.get_least_squares(
                                qb.get_trx_dlp_result(gtm_ids),
                                ea=ea,
                                plot_name='Least Squares Analysis, ea: ' +
                                str(ea) + '\n' + key,
                                save_plot=save_plot
                            )
                            df_lst_temp = pd.DataFrame(index=[key], data=[[vg_min, vg_max, fi, coh, E, E_per_n, eps, N]],
                                                       columns=['MIN(VG)', 'MAX(VG)', 'FI', 'COH', 'ABS. SQ. ERR.', 'ABS. SQ. ERR./N', 'MEAN REL. ERR. %', 'N'])
                            ls_list.append(df_lst_temp)
                    if len(ls_list) > 0:
                        df_ls_stat = pd.concat(ls_list)
                        df_ls_stat.index.name = 'ea: ' + str(ea) + '%'
                        df_lst_sqrs_dict.update(
                            {str(ea) + r'% rek least squares fit': df_ls_stat})
                    if len(avg_list) > 0:
                        df_avg_stat = pd.concat(avg_list)
                        df_avg_stat.index.name = 'ea: ' + str(ea) + '%'
                        df_vg_stat_dict.update(
                            {str(ea) + r'% rek gemiddelde fit': df_avg_stat})

                for ea in rek_selectie:
                    bbn_list = []
                    for bbn_code in pd.unique(df_trx.BBN_KODE):
                        gtm_ids = df_trx[df_trx.BBN_KODE == bbn_code].GTM_ID
                        if len(gtm_ids > 0):
                            df_trx_results_temp = qb.get_trx_result(gtm_ids)
                            mean_fi, std_fi, mean_coh, std_coh, N = qb.get_average_per_ea(
                                df_trx_results_temp, ea)
                            bbn_list.append(pd.DataFrame(index=[bbn_code], data=[[mean_fi, mean_coh, std_fi, std_coh, N]],
                                                         columns=['MEAN(FI)', 'MEAN(COH)', 'STD(FI)', 'STD(COH)', 'N']))
                    if len(bbn_list) > 0:
                        df_bbn_stat = pd.concat(bbn_list)
                        df_bbn_stat.index.name = 'ea: ' + str(ea) + '%'
                        df_bbn_stat_dict.update(
                            {str(ea) + r'% rek per BBN code': df_bbn_stat})

        # Check if the .xlsx file exists
        output_file_dir = os.path.join(output_location, output_file)
        if os.path.exists(output_file_dir):
            name, ext = output_file.split('.')
            i = 1
            while os.path.exists(os.path.join(output_location, name + '{}.'.format(i) + ext)):
                i += 1
            output_file_dir = os.path.join(
                output_location, name + '{}.'.format(i) + ext)

        # At the end of the 'with' function it closes the excelwriter automatically, even if there was an error
        # writer in append mode so that the NEN tables are kept
        with pd.ExcelWriter(output_file_dir, engine='xlwt', mode='w') as writer:
            for key in df_dict:
                # Writing every dataframe in the dictionary to a different sheet
                df_dict[key].to_excel(writer, sheet_name=key)

            if df_trx is not None:
                # Write the multiple dataframes of the same statistical analysis for TRX to the same excel sheet by counting rows
                if df_vg_stat_dict:
                    row = 0
                    for key in df_vg_stat_dict:
                        df_vg_stat_dict[key].to_excel(
                            writer, sheet_name='Simpele Vg stat.', startrow=row)
                        row = row + len(df_vg_stat_dict[key].index) + 2
                # Repeat...
                if df_lst_sqrs_dict:
                    row = 0
                    for key in df_lst_sqrs_dict:
                        df_lst_sqrs_dict[key].to_excel(
                            writer, sheet_name='Least Squares Vg Stat.', startrow=row)
                        row = row + len(df_lst_sqrs_dict[key].index) + 2
                if df_bbn_stat_dict:
                    row = 0
                    for key in df_bbn_stat_dict:
                        df_bbn_stat_dict[key].to_excel(
                            writer, sheet_name='bbn_kode Stat.', startrow=row)
                        row = row + len(df_bbn_stat_dict[key].index) + 2

        os.startfile(output_file_dir)


class ProevenVerzamelingTask(QgsTask):
    """Creating a task to run all the heavy processes in the background on a different thread"""

    def __init__(self, description, iface, **kwargs):
        super().__init__(description, QgsTask.CanCancel)
        self.iface = iface
        self.exception = None
        self.traceback = None

        self.qb = kwargs.get('qb')
        self.selected_layer = kwargs.get('selected_layer')
        self.output_location = kwargs.get('output_location')
        self.output_name = kwargs.get('output_name')
        self.maxH = kwargs.get('maxH', 1000)
        self.minH = kwargs.get('minH', -1000)
        self.maxVg = kwargs.get('maxVg', 40)
        self.minVg = kwargs.get('minVg', 0)
        
        self.trx_bool = kwargs.get('trx_bool', False)
        if self.trx_bool:
            self.ea = kwargs.get('ea', [2])
            self.proef_types = kwargs.get('proef_types', ['CU'])
            self.volG_trx = kwargs.get('volG_trx')
            self.save_plot = kwargs.get('save_plot', False)

        self.sdp_bool = kwargs.get('sdp_bool', False)
        if self.sdp_bool:
            self.volG_sdp = kwargs.get('volG_sdp')

    def run(self):
        """
        Is called when the QgsTask is ran in the background. 
        No exception can be raised inside a QgsTask therefore we catch them only raise
        them when we are in finished(). Finished() gets called from the main thread and
        can therefore raise exceptions.
        """
        try:
            result = self.get_data()
            if result:
                return True
            else:
                return False
        except Exception as e:
            self.exception = e
            self.traceback = traceback.format_exc()
            return False

    def finished(self, result):
        """
        This function is automatically called when the task has
        completed (successfully or not).
        You implement finished() to do whatever follow-up stuff
        should happen after the task is complete.
        finished is always called from the main thread, so it's safe
        to do GUI operations and raise Python exceptions here.
        result is the return value from self.run.
        """
        if result:
            self.iface.messageBar().pushMessage(
                'Task "{name}" completed in {duration} seconds.'.format(
                    name=self.description(),
                    duration=round(self.elapsedTime()/1000, 2)),
                Qgis.Info,
                duration=3)
        else:
            if self.exception is None:
                self.iface.messageBar().pushMessage(
                    'RandomTask "{name}" not successful but without '
                    'exception (probably the task was manually '
                    'canceled by the user)'.format(
                        name=self.description()),
                    Qgis.Warning,
                    duration=3)
            else:
                self.iface.messageBar().pushMessage(
                    'RandomTask "{name}" Exception: {exception}, Traceback: {traceback}'.format(
                        name=self.description(),
                        exception=self.exception,
                        traceback=self.traceback),
                    Qgis.Critical,
                    duration=10)
                raise self.exception

    def cancel(self):
        self.iface.messageBar().pushMessage(
            'Task "{name}" was canceled.'.format(
                task=self.description()),
            Qgis.Info, duration=3)
        super().cancel()

    def get_data(self):

        self.setProgress(0)

        output_file = self.output_name + '.xlsx'

        # Check if the directory still has to be made.
        if os.path.isdir(self.output_location) is False:
            os.mkdir(self.output_location)

        # Extract the loc ids from the selected points in the selected layer
        loc_ids = self.qb.get_loc_ids(self.selected_layer)
        loc_ids = [int(x) for x in loc_ids]
        if self.isCanceled():
            return False
        self.setProgress(10)

        # Get all meetpunten related to these loc_ids
        df_meetp = self.qb.get_meetpunten(loc_ids)
        df_geod = self.qb.get_geo_dossiers(df_meetp.GDS_ID)

        if self.isCanceled():
            return False
        self.setProgress(20)

        df_gm = self.qb.get_geotech_monsters(loc_ids)
        if df_gm is not None:
            df_gm_filt_on_z = self.qb.select_on_z_coord(df_gm, self.maxH, self.minH)
            if df_gm_filt_on_z is None:
                raise ValueError(
                    "There are no Geotechnische monsters in this depth range. {} to {} mNAP".format(self.maxH, self.minH))

        # Add the df_meetp, df_geod and df_gm_filt_on_z to a dataframe dictionary
        df_dict = {'BIS_Meetpunten': df_meetp, 'BIS_GEO_Dossiers': df_geod,
                    'BIS_Geotechnische_Monsters': df_gm_filt_on_z}

        if self.isCanceled():
            return False
        self.setProgress(30)

        if self.trx_bool:
            dict_trx, dict_lstsq_stat, fig_list, dict_bbn_stat = \
                self.trx(df_gm_filt_on_z.GTM_ID)
            df_dict.update(dict_trx)

        if self.isCanceled():
            return False
        self.setProgress(60)

        if self.sdp_bool:
            dict_sdp = self.sdp(df_gm_filt_on_z)
            df_dict.update(dict_sdp)
        
        if self.isCanceled():
            return False
        self.setProgress(80)

        output_file_dir = os.path.join(self.output_location, output_file)
        if os.path.exists(output_file_dir):
            name, ext = output_file.split('.')
            i = 1
            while os.path.exists(os.path.join(self.output_location, name + '{}.'.format(i) + ext)):
                i += 1
            output_file_dir = os.path.join(self.output_location, name + '{}.'.format(i) + ext)

        # At the end of the 'with' function it closes the excelwriter automatically, even if there was an error
        # untrue: writer in append mode so that the NEN tables are kept
        with pd.ExcelWriter(output_file_dir, engine='xlsxwriter', mode='w') as writer:
            for key in df_dict:
                # Writing every dataframe in the dictionary to a different sheet
                df_dict[key].to_excel(writer, sheet_name=key)

                if self.trx_bool:
                    # Write the multiple dataframes of the same statistical analysis for TRX to the same excel sheet by counting rows
                    if dict_lstsq_stat:
                        row = 0
                        for key in dict_lstsq_stat:
                            dict_lstsq_stat[key].to_excel(
                                writer, sheet_name='Least Squares Vg Stat.', startrow=row)
                            row = row + len(dict_lstsq_stat[key].index) + 2
                    if dict_bbn_stat:
                        row = 0
                        for key in dict_bbn_stat:
                            dict_bbn_stat[key].to_excel(
                                writer, sheet_name='bbn_kode Stat.', startrow=row)
                            row = row + len(dict_bbn_stat[key].index) + 2
                    if self.save_plot:
                        i = 1
                        for fig in fig_list:
                            fig.savefig(os.path.join(self.output_location, 'fig_{}.pdf'.format(i)))
                            i = i + 1

        if self.isCanceled():
            return False
        self.setProgress(100)
        return True

    def trx(self, gtm_ids):
            
        rek_selectie = [self.ea]

        df_trx = self.qb.get_trx(gtm_ids, proef_type=self.proef_types)

        df_trx = self.qb.select_on_vg(df_trx, self.maxVg, self.minVg)
        # Get all TRX results, TRX deelproeven and TRX deelproef results
        df_trx_results = self.qb.get_trx_result(df_trx.GTM_ID)
        df_trx_dlp = self.qb.get_trx_dlp(df_trx.GTM_ID)
        df_trx_dlp_result = self.qb.get_trx_dlp_result(df_trx.GTM_ID)

        self.setProgress(40)

        df_dict = {'BIS_TRX_Proeven': df_trx, 'BIS_TRX_Results': df_trx_results,
                        'BIS_TRX_DLP': df_trx_dlp, 'BIS_TRX_DLP_Results': df_trx_dlp_result}
        df_bbn_stat_dict = {}
        df_lst_sqrs_dict = {}
        fig_list = []
        # Doing statistics on the select TRX proeven
        if len(df_trx.index) > 1:

            if self.volG_trx is None:
                # Create a linear space between de maximal volumetric weight and the minimal volumetric weight
                minvg, maxvg = min(df_trx.VOLUMEGEWICHT_NAT), max(
                    df_trx.VOLUMEGEWICHT_NAT)
                N = round(len(df_trx.index) / 5) + 1
                cutoff = 1  # The interval cant be lower than 1 kn/m3
                if (maxvg-minvg)/N > cutoff:
                    Vg_linspace = np.linspace(minvg, maxvg, N)
                else:
                    N = round((maxvg-minvg)/cutoff)
                    if N < 2:
                        Vg_linspace = np.linspace(minvg, maxvg, 2)
                    else:
                        Vg_linspace = np.linspace(minvg, maxvg, N)

                    Vgmax = Vg_linspace[1:]
                    Vgmin = Vg_linspace[0:-1]
            else:
                Vgmax = self.volG_trx[1:]
                Vgmin = self.volG_trx[0:-1]
            
            self.setProgress(45)

            for ea in rek_selectie:
                ls_list = []
                for vg_max, vg_min in zip(Vgmax, Vgmin):
                    # Make a selection for this volumetric weight interval
                    gtm_ids = self.qb.select_on_vg(
                        df_trx, Vg_max=vg_max, Vg_min=vg_min, soort='nat')['GTM_ID']
                    if len(gtm_ids) > 0:
                        # Create a tag for this particular volumetric weight interval
                        key = 'Vg: ' + str(round(vg_min, 1)) + \
                            '-' + str(round(vg_max, 1)) + ' kN/m3'
                        # Get the related TRX results...
                        #
                        # Potentially the next line could be done without querying the database again
                        # for the data that is already availabe in the variable df_trx_results
                        # but I have not found the right type of filter methods in Pandas which
                        # can replicate the SQL filters
                        #            
                        # Calculate the least squares estimate of the S en T and add them to a dataframe list
                        fi, coh, E, E_per_n, eps, N, fig = self.qb.get_least_squares(                            
                            self.qb.get_trx_dlp_result(gtm_ids),
                            ea=ea,
                            plot_name='Least Squares Analysis, ea: ' +
                            str(ea) + '\n' + key,
                            save_plot=self.save_plot
                        )
                        fig_list.append(fig)
                        df_lst_temp = pd.DataFrame(index=[key], data=[[vg_min, vg_max, fi, coh, E, E_per_n, eps, N]],
                                                columns=['MIN(VG)', 'MAX(VG)', 'FI', 'COH', 'ABS. SQ. ERR.', 'ABS. SQ. ERR./N', 'MEAN REL. ERR. %', 'N'])
                        ls_list.append(df_lst_temp)
                if len(ls_list) > 0:
                    df_ls_stat = pd.concat(ls_list)
                    df_ls_stat.index.name = 'ea: ' + str(ea) + '%'                    
                    df_lst_sqrs_dict.update(
                        {str(ea) + r'% rek least squares fit': df_ls_stat})
        
        return df_dict, df_lst_sqrs_dict, fig_list, df_bbn_stat_dict

    def sdp(self, gtm_ids):
        df_sdp = self.qb.get_sdp(gtm_ids)
        if df_sdp is not None:
            df_sdp = self.qb.select_on_vg(df_sdp, self.maxVg, self.minVg)
        if df_sdp is not None:
            df_sdp_result = self.qb.get_sdp_result(df_sdp.GTM_ID)
            df_dict = {'BIS_SDP_Proeven': df_sdp,
                    'BIS_SDP_Resultaten': df_sdp_result}
        return df_dict

