__author__ = 'Vince.ec'

from grizli import model
from grizli import multifit
import numpy as np
from scipy.interpolate import interp1d
from astropy.table import Table
from astropy import wcs
from astropy.io import fits
from glob import glob
import os

def Extract_BeamCutout(target_id, grism_file, mosaic, seg_map, instruement, catalog):
    flt = model.GrismFLT(grism_file = grism_file ,
                          ref_file = mosaic, seg_file = seg_map,
                            pad=200, ref_ext=0, shrink_segimage=True, force_grism = instrument)
    
    # catalog / semetation image
    ref_cat = Table.read(catalog ,format='ascii')
    seg_cat = flt.blot_catalog(ref_cat,sextractor=False)
    flt.compute_full_model(ids=seg_cat['id'])
    beam = flt.object_dispersers[target_id][2]['A']
    co = model.BeamCutout(flt, beam, conf=flt.conf)
    
    PA = np.round(fits.open(grism_file)[0].header['PA_V3'] , 1)
    
    co.write_fits(root='beams/o{0}'.format(PA), clobber=True)

    ### add EXPTIME to extension 0
    
    
    fits.setval('beams/o{0}_{1}.{2}.A.fits'.format(PA, target_id, instrument), 'EXPTIME', ext=0,
            value=fits.open('beams/o{0}_{1}.{2}.A.fits'.format(PA, target_id, instrument))[1].header['EXPTIME'])   

def Scale_model(data, sigma, model):
    return np.sum(((data * model) / sigma ** 2)) / np.sum((model ** 2 / sigma ** 2))

class Gen_spec(object):
    def __init__(self, beam, redshift, spec_file, minwv = 7800, maxwv = 11200):
        self.beam = model.BeamCutout(fits_file = beam)
        self.redshift = redshift
        self.gal_wv, self.gal_fl, self.gal_er = np.load(spec_file)
        
        """ 


        """

        IDX = [U for U in range(len(self.gal_wv)) if minwv <= self.gal_wv[U] <= maxwv]

        self.gal_wv_rf = self.gal_wv[IDX] / (1 + self.redshift)
        self.gal_wv = self.gal_wv[IDX]
        self.gal_fl = self.gal_fl[IDX]
        self.gal_er = self.gal_er[IDX]

        ## Get sensitivity function
        flat = self.beam.flat_flam.reshape(self.beam.beam.sh_beam)
        fwv, ffl, e = self.beam.beam.optimal_extract(flat, bin=0)
        
        self.filt = interp1d(fwv, ffl)(self.gal_wv)
        
    def Sim_spec(self, model_file, model_redshift = 0, dust = 0):
        model_wv, model_fl = np.load(model_file)
        
        if model_redshift ==0:
            model_redshift = self.redshift 
        
        ## Compute the models
        self.beam.compute_model(spectrum_1d=[model_wv*(1+model_redshift),model_fl])

        ## Extractions the model (error array here is meaningless)
        w, f, e = self.beam.beam.optimal_extract(self.beam.model , bin=0)

        ifl = interp1d(w, f)(self.gal_wv)
        
        C = Scale_model(self.gal_fl, self.gal_er, ifl / self.filt)

        self.fl = C * ifl / self.filt
        
class Gen_MB_spec(object):
    def __init__(self, beams, redshift, spec_file, minwv = 7800, maxwv = 11200):
        self.mb = multifit.MultiBeam(beams)
        self.redshift = redshift
        self.gal_wv, self.gal_fl, self.gal_er = np.load(spec_file)
        
        """ 


        """

        IDX = [U for U in range(len(self.gal_wv)) if minwv <= self.gal_wv[U] <= maxwv]

        self.gal_wv_rf = self.gal_wv[IDX] / (1 + self.redshift)
        self.gal_wv = self.gal_wv[IDX]
        self.gal_fl = self.gal_fl[IDX]
        self.gal_er = self.gal_er[IDX]

        ## Get sensitivity function
        flat = self.mb.optimal_extract(self.mb.flat_flam[self.mb.fit_mask])
        
        self.filt = interp1d(flat['G102']['wave'], flat['G102']['flux'])(self.gal_wv)
        
    def Sim_spec(self, model_file, model_redshift = 0, dust = 0):
        mwv, mfl = np.load(model_file)
        
        if model_redshift ==0:
            model_redshift = self.redshift 
        
        ## Create model
        spec = self.mb.get_flat_model(spectrum_1d = [mwv *(1 + model_redshift), mfl])

        ## Extract model and flat
        sp = self.mb.optimal_extract(spec)
        
        ifl = interp1d(sp['G102']['wave'], sp['G102']['flux'])(self.gal_wv)
        
        C = Scale_model(self.gal_fl, self.gal_er, ifl / self.filt)

        self.fl = C * ifl / self.filt