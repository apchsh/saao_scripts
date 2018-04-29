###############################################################################
# ======== PHOTOMETRY SCRIPT FOR SAAO DATA BASED ON THE SEP LIBRARY ========= #
###############################################################################

import sys
import fitsio
import sep
import numpy as np
import matplotlib.pyplot as plt 
import unpack
from astropy.table import Table
from os import path
from glob import glob
from random import uniform
from donuts import Donuts
from time import time as time_
from scipy import ndimage

def makeheader(h, dateobs, observer, telescop, instrumt, filtera,
        filterb, obj, ra, dec, epoch, equinox, platescale):
    #Make general header for each HDU
    hlist = [{'name':'DATE-OBS', 'value':h[dateobs],
                    'comment':h.get_comment(dateobs)},
            {'name':'OBSERVER', 'value':h[observer],
                    'comment':h.get_comment(observer)},
            {'name':'OBSERVAT', 'value':'SAAO',
                    'comment':'Observatory'},
            {'name':'TELESCOP', 'value':h[telescop],
                    'comment':h.get_comment(telescop)},
            {'name':'INSTRUMT', 'value':h[instrumt],
                    'comment':h.get_comment(instrumt)},
            {'name':'FILTERA', 'value':h[filtera],
                    'comment':h.get_comment(filtera)},
            {'name':'FILTERB', 'value':h[filterb],
                    'comment':h.get_comment(filterb)},
            {'name':'PLATESCL', 'value':platescale, 'comment':'arcsec/pixel'},
            {'name':'OBJECT', 'value':h[obj], 'comment':h.get_comment(obj)},
            {'name':'RA', 'value':h[ra], 'comment':h.get_comment(ra)},
            {'name':'DEC', 'value':h[dec], 'comment':h.get_comment(dec)},
            {'name':'EPOCH', 'value':h[epoch],
                    'comment':h.get_comment(epoch)},
            {'name':'EQUINOX', 'value':h[equinox],
                    'comment':h.get_comment(equinox)}
            ]
    return hlist

def rot(image, xy, angle):
    #Rotate an input image and set of coordinates by an angle
    im_rot = ndimage.rotate(image,angle) 
    org_center = (np.array(image.shape[:2][::-1])-1)/2.
    rot_center = (np.array(im_rot.shape[:2][::-1])-1)/2.
    xy_rot = np.empty([2, xy.shape[1]])
    for i in range(xy.shape[1]):
        org = xy[:,i]-org_center
        a = np.deg2rad(angle)
        xy_rot[:,i] = np.array([org[0]*np.cos(a) + org[1]*np.sin(a),
            -org[0]*np.sin(a) + org[1]*np.cos(a) ] + rot_center)
    return im_rot, xy_rot

def star_loc_plot(name, data, x, y, angle):

    dmean = np.mean(data)
    dstd = np.std(data)
    
    fig = plt.figure()
    data_rot, (x,y) = rot(data, np.vstack([x,y]), angle)
    plt.imshow(data_rot, vmin=dmean-1*dstd, vmax=dmean+2*dstd,
           cmap=plt.get_cmap('gray'))
    color_range=plt.cm.hsv(np.linspace(0,1,10))
   
    ind = x.shape[0]
    for i in range(0, int(ind)):
        plt.text(x[i], y[i], "%i" % i, fontsize=16)
        #, color=color_range[int(ind[i])])
            
    plt.savefig(name, bbox_inches="tight")
    plt.close('all')

def build_obj_cat(dir_, name, first, thresh, bw, fw, angle):
    
    #Get background image  
    bkg = sep.Background(first, bw=bw, bh=bw, fw=fw, fh=fw)

    #Subtract the background
    first_sub = first - bkg.back() 

    #Extract sources to use as object catalogue
    objects = sep.extract(first_sub, thresh=thresh, err=bkg.globalrms)

    #Get the half-width radius 
    fwhm_ref, flags = sep.flux_radius(first_sub, objects['x'],
            objects['y'], np.ones(len(objects['x']))*10.0, 0.5, subpix=10)
   
    #Update the object centroid positions using sep winpos algorithm
    x_ref, y_ref, f_ref = sep.winpos(first_sub, objects['x'], 
            objects['y'], fwhm_ref*0.424, subpix=10)
    '''
    #Or alternatively just use Donuts positions without winpos refinement
    x_ref = objects['x']
    y_ref = objects['y']
    '''
    
    #Save example field image with objects numbered
    star_loc_plot(path.join(dir_, "SAAO_"+ name +'_field.png'),
            first_sub, x_ref, y_ref, angle)
    
    return x_ref, y_ref

def run_phot(dir_, p, name):

    '''THE FOLLOWING DEFINITIONS NEED TO BE READ IN FROM FILE EVENTUALLY'''
    #Define background box sizes to use
    bsizes = np.array(p.box_size)

    #Define background filter widths to use
    fsizes = np.array(p.filter_size)

    #Define aperture radii to use for flux measurements
    radii = np.array(p.radii)

    #Define num apertures and radius to use for bkg residuals
    bkg_rad = 4.0
    nbapps = 100

    #Define platescale for seeing calculation
    platescale = p.platescale #arcsec / pix
    
    #Define source detection threshold
    thresh = p.source_thresh
   
    #Define rotation angle for field image
    field_angle = p.field_angle

    #Define header keywords
    hOBJECT = "OBJECT"
    hRA = "OBJRA"
    hDEC = "OBJDEC"
    hEPOCH = "OBJEPOCH"
    hEQUINOX = "OBJEQUIN"
    hGAIN = "PREAMP"
    hEXP = "EXPOSURE"
    hBINFAC = "VBIN"
    hAIRMASS = "AIRMASS"
    hJD = "JD"
    hHJD = "HJD"
    hBJD = "BJD"
    hOBSLAT = "LAT" # Needed for non-SAAO telescopes
    hOBSLONG = "LON" # Needed for non-SAAO telescopes
    hOBSALT = "ALT" # Needed for non-SAAO telescopes
    hOBSERVER = "OBSERVER"
    hOBSERVAT = "OBSERVAT" # Needed for non-SAAO telescopes
    hTELESCOP = "TELESCOP"
    hINSTRUMT = "INSTRUME"
    hFILTERA = "FILTERA"
    hFILTERB = "FILTERB"
    hDATEOBS = "GPSSTART"

    #Define output file name 
    output_name = path.join(dir_, "SAAO_"+ name +'_phot.fits')

    '''END OF DEFINITIONS'''

    #Get science images
    file_dir_ = dir_ + name + '/'
    f_list = sorted(glob(file_dir_ + "*.fits")) 
    print ("%d frames" %len(f_list))

    #Load first image
    with fitsio.FITS(f_list[0]) as fi:
        first = fi[0][:, :]
        firsthdr = fi[0].read_header()

    #Get object catalogue x and y positions
    x_ref, y_ref = build_obj_cat(dir_, name, first, thresh, 32, 3, field_angle)

    #Define aperture positions for background flux measurement
    lim_x = first.shape[0]
    lim_y = first.shape[1]
    bapp_x = [uniform(0.05*lim_x, 0.95*lim_x) for n in range(nbapps)]
    bapp_y = [uniform(0.05*lim_y, 0.95*lim_y) for n in range(nbapps)]
    
    #Initialise variables to store data
    '''4D array structure: [apertures, objects, bkg_params, frames]'''
    flux_store = np.empty([radii.shape[0], len(x_ref),
        len(bsizes)*len(fsizes), len(f_list)])
    fluxerr_store = np.empty([radii.shape[0], len(x_ref),
        len(bsizes)*len(fsizes), len(f_list)])
    flag_store = np.empty([radii.shape[0], len(x_ref),
        len(bsizes)*len(fsizes), len(f_list)])
    bkg_app_flux_store = np.empty([radii.shape[0], len(x_ref),
        len(bsizes)*len(fsizes), len(f_list)])
    bkg_app_fluxerr_store = np.empty([radii.shape[0], len(x_ref),
        len(bsizes)*len(fsizes), len(f_list)])
    
    '''3D array structure: [bkg_apertures, bkg_params, frames]'''
    bkg_flux_store = np.empty([len(bapp_x), len(bsizes)*len(fsizes),
        len(f_list)])
    
    '''2D array structure: [objects, frames]'''
    pos_store_x = np.empty([len(x_ref), len(f_list)])
    pos_store_y = np.empty([len(y_ref), len(f_list)])
    pos_store_donuts_x = np.empty([len(x_ref), len(f_list)])
    pos_store_donuts_y = np.empty([len(y_ref), len(f_list)])
    
    '''2D array structure: [bkg_params, frames]'''
    fwhm_store = np.empty([len(bsizes)*len(fsizes), len(f_list)])
    
    '''1D array structure: [frames]'''
    jd_store = np.empty([len(f_list)])
    hjd_store = np.empty([len(f_list)])
    bjd_store = np.empty([len(f_list)])
    frame_shift_x_store = np.empty([len(f_list)])
    frame_shift_y_store = np.empty([len(f_list)])
    exp_store = np.empty([len(f_list)])
    airmass_store = np.empty([len(f_list)])

    #Create Donuts object using first image as reference
    d = Donuts(
        refimage=f_list[0], image_ext=0,
        overscan_width=0, prescan_width=0,
        border=0, normalise=False,
        subtract_bkg=False)
    
    print "Starting photometry for %s." % name

    #Initialise start time for progress meter 
    meter_width=48
    start_time = time_()

    #Iterate through each reduced science image
    for count, file_  in enumerate(f_list): 
               
        #Store frame offset wrt reference image
        if count != 1:
            #Calculate offset from reference image
            shift_result = d.measure_shift(file_)
            frame_shift_x_store[count-1] = (shift_result.x).value
            frame_shift_y_store[count-1] = (shift_result.y).value
        else:
            #Frame is the reference image so no offset by definition
            frame_shift_x_store[count-1] = 0
            frame_shift_y_store[count-1] = 0

        #Create image handle
        with fitsio.FITS(file_) as f:
            
            #Load tabular data from image
            data = f[0][:, :]
            header = f[0].read_header()

            #Load header data from image
            ra = header[hRA]
            dec = header[hDEC]
            jd = header[hJD]
            try:
                hjd = header[hHJD]
            except:
                hjd = np.nan
            try:
                bjd = header[hBJD]
            except:
                bjd = np.nan
            exp = header[hEXP]
            gain = header[hGAIN]
            binfactor = header[hBINFAC]
            airmass = header[hAIRMASS]
    
        # Store frame-only dependent times
        jd_store[count-1] = jd
        hjd_store[count-1] = hjd
        bjd_store[count-1] = bjd
        exp_store[count-1] = exp
        if type(airmass) == float:
            airmass_store[count-1] = airmass
        else:
            airmass_store[count-1] = 0.0

        #Initialise count of number of bkg params gone through
        bkg_count = 0

        #Iterate through background box sizes
        for ii in bsizes:
            #iterate through filter widths
            for jj in fsizes:

                #Get background image  
                bkg = sep.Background(data, bw=ii, bh=ii, fw=jj, fh=jj)

                #Subtract the background from data
                data_sub = data - bkg.back()

                '''Extract objects at minimal detection threshold to properly
                mask stars for bkg residual measurement'''
                objects_bkg, segmap_bkg = sep.extract(data_sub, thresh=1.0, 
                        err=bkg.globalrms, segmentation_map=True)
                
                #Measure background flux residuals
                bflux, bfluxerr, bflag = sep.sum_circle(data_sub, bapp_x, bapp_y,
                            bkg_rad, err=bkg.globalrms, mask=segmap_bkg, gain=gain)
                
                #Store background flux residuals
                bkg_flux_store[:, bkg_count, count-1] = bflux/exp
                
                '''Adjust target aperture centroid positions using Donuts output to
                allow for drift of frame compared to reference image'''
                x = x_ref - frame_shift_x_store[count-1]
                y = y_ref - frame_shift_y_store[count-1]
                    
                #Get object half width radii
                fwhm, flags = sep.flux_radius(data_sub, x, y,
                        np.ones(len(x))*10.0, 0.5, subpix=10)

                #Store the fwhm result in arcsec, taking mean over all objects
                fwhm_store[bkg_count, count-1] = (
                        np.nanmean(fwhm) * binfactor * platescale)
                
                #Update target aperture positions using winpos algorithm
                x_pos,y_pos,f = sep.winpos(data_sub, x, y,
                        fwhm*0.424, subpix=10)
                '''
                #Or alternatively trust Donuts positions without winpos
                #refinement
                x_pos = x
                y_pos = y
                '''
                
                #Store the object centroid positions 
                pos_store_x[:, count-1] = x_pos
                pos_store_y[:, count-1] = y_pos
                pos_store_donuts_x[:, count-1] = x
                pos_store_donuts_y[:, count-1] = y

                #Tile centroid x/y positions per aperture radii used
                x_rad = np.tile(x_pos, len(radii))
                y_rad = np.tile(y_pos, len(radii))
                x_rad = x_rad.reshape((len(radii), len(x_pos)))
                y_rad = y_rad.reshape((len(radii), len(y_pos)))

                #Tile list of aperture radii per object in catalogue and transpose
                rad = [] 
                for z  in range(0, len(x_ref)):
                    rad.append(radii)
                rad = np.asarray(rad).transpose()
                
                #Measure number of counts in target aperture
                flux, fluxerr, flag = sep.sum_circle(data_sub, x_rad, y_rad,
                    rad, err=bkg.globalrms, gain=gain)
                
                #Measure num counts subtracted as bkg in same aperture
                bflux_app, bfluxerr_app, bflag_app = sep.sum_circle(
                        bkg.back(), x_rad, y_rad, rad, err=bkg.globalrms, gain=gain)

                #Store flux, flux err and flags for target apertures
                flux_store[:, :, bkg_count, count-1] = flux/exp
                fluxerr_store[:, :, bkg_count, count-1] = fluxerr/exp
                flag_store[:, :, bkg_count, count-1] = flag

                #Store flux, flux err and flags for bkg in same apertures
                bkg_app_flux_store[:, :, bkg_count, count-1] = bflux_app/exp
                bkg_app_fluxerr_store[:, :, bkg_count, count-1] = bfluxerr_app/exp
                
                #Increment count of bkg_params gone through
                bkg_count += 1
    
        #Show progress meter for number of frames processed
        n_steps = len(f_list)
        nn = int((meter_width+1) * float(count) / n_steps)
        delta_t = time_()-start_time # time to do float(count) / n_steps % of caluculation
        time_incr = delta_t/(float(count+1) / n_steps) # seconds per increment
        time_left = time_incr*(1- float(count) / n_steps)
        m, s = divmod(time_left, 60)
        h, m = divmod(m, 60)
        sys.stdout.write("\r[{0}{1}] {2:5.1f}% - {3:02}h:{4:02}m:{05:.2f}s".
             format('#' * nn, ' ' * (meter_width - nn), 100*float(count)/n_steps,h,m,s))
  
    #Get output file general header
    hdr = makeheader(firsthdr, hDATEOBS, hOBSERVER, hTELESCOP,
        hINSTRUMT, hFILTERA, hFILTERB, hOBJECT, hRA, hDEC, hEPOCH, hEQUINOX,
        platescale)

    #Save each data array as a HDU in FITS file
    with fitsio.FITS(output_name, "rw") as g:
        g.write(flux_store, header=hdr, extname="OBJ_FLUX")
        g.write(fluxerr_store, header=hdr, extname="OBJ_FLUX_ERR")
        g.write(flag_store, header=hdr, extname="OBJ_FLUX_FLAGS")
        g.write(bkg_app_flux_store, header=hdr, extname="OBJ_BKG_APP_FLUX")
        g.write(bkg_app_fluxerr_store, header=hdr,
                extname="OBJ_BKG_APP_FLUX_ERR")
        g.write(bkg_flux_store, header=hdr, extname="RESIDUAL_BKG_FLUX")
        g.write(pos_store_x, header=hdr, extname="OBJ_CCD_X")
        g.write(pos_store_y, header=hdr, extname="OBJ_CCD_Y")
        g.write(pos_store_donuts_x, header=hdr, extname="OBJ_CCD_X_UNREFINED")
        g.write(pos_store_donuts_y, header=hdr, extname="OBJ_CCD_Y_UNREFINED")
        g.write(fwhm_store, header=hdr, extname="MEAN_OBJ_FWHM")
        g.write(jd_store, header=hdr, extname="JD")
        g.write(hjd_store, header=hdr, extname="HJD")
        g.write(bjd_store, header=hdr, extname="BJD")
        g.write(frame_shift_x_store, header=hdr, extname="FRAME_SHIFT_X")
        g.write(frame_shift_y_store, header=hdr, extname="FRAME_SHIFT_Y")
        g.write(frame_shift_y_store, header=hdr, extname="FRAME_SHIFT_Y")
        g.write(exp_store, header=hdr, extname="EXPOSURE_TIME")
        g.write(airmass_store, header=hdr, extname="AIRMASS")


    print "\nCompleted photometry for %s." % name
