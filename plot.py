#============ LC Plotting Script for SAAO Pipeline Photometry Output ==========#
# 1) Place this file in the same directory containing the reduction directory 
# generated by the SAAO pipeline created by Alex Chaushev.
#
# 2) Identify target and comparison object numbers from annotated map generated
# by SAAO pipeline.
#
# 3) Change variables below accordingly and run script
#==============================================================================#

import numpy as np
import matplotlib.pyplot as plt
import warnings; warnings.simplefilter('ignore') 
import sys

from astropy.stats import sigma_clip
from os.path import join
from astropy.table import Table
from fitsio import FITS
from glob import glob

warnings.simplefilter('ignore')

def get_sn_max(sn_max):
    sn_max_a = sn_max[0][0]
    sn_max_b = sn_max[1][0]
    return sn_max_a, sn_max_b

def bin_to_size(data, num_points_bin, block_exposure_times, 
        block_index_boundaries, mask):
    '''Convenience function to bin everything to a fixed num of points per
    bin. Data is clipped to the nearest bin (i.e. data % num_points_bin are
    discarded from the end of the time series).'''
    
    #Initialise storeage for blocks
    data_rack = []

    #Iterate over blocks
    for j, value in enumerate(block_index_boundaries):
        if j < len(block_index_boundaries) -1:
            #Get block
            data_block = data[value:block_index_boundaries[j+1]]
            mask_block = mask[value:block_index_boundaries[j+1]]
            
            #Clean out nans from block
            data_block = data_block[mask_block]

            #Calculate number of points per bin for block
            npb = num_points_bin / block_exposure_times[j]

            #bin block
            num_bins = int(len(data_block) / npb)
            data_block = rebin(data_block[0:num_bins*npb], num_bins)

            #Store block in rack
            data_rack.append(data_block)

    #Flatten rack
    rebinned_data = np.hstack(data_rack)
    return rebinned_data

def rebin(a, *args):
    '''From the scipy cookbook on rebinning arrays
    rebin ndarray data into a smaller ndarray of the same rank whose dimensions
    are factors of the original dimensions. eg. An array with 6 columns and 4 
    rows can be reduced to have 6,3,2 or 1 columns and 4,2 or 1 rows.
    example usages:
    a=rand(6,4); b=rebin(a,3,2)
    a=rand(6); b=rebin(a,2)'''
    shape = a.shape
    lenShape = len(shape)
    factor = np.asarray(shape)/np.asarray(args)
    evList = ['a.reshape('] + \
             ['args[%d],factor[%d],'%(i,i) for i in range(lenShape)] + \
             [')'] + ['.sum(%d)'%(i+1) for i in range(lenShape)] + \
             ['/factor[%d]'%i for i in range(lenShape)]
    return eval(''.join(evList))

def air_corr(flux, xjd, xjd_oot_l=99, xjd_oot_u=99):
    '''Function to remove a 2-D polynomial fit using the out of transit
    region.'''
    
    #Copy data to prevent overwriting input arrays
    flux_r = np.copy(flux)
    xjd_r = np.copy(xjd)

    #Divide out residual airmass using out of transit region
    oot = (((xjd_r < xjd_oot_l) | (xjd_r > xjd_oot_u)) & (np.isfinite(flux_r)) &
        (np.isfinite(xjd_r)))
    poly1 = np.poly1d(np.polyfit(xjd_r[oot], flux_r[oot], 2))
    p1 = poly1(xjd_r)
    flux_r /= p1
    return flux_r

def make_lc_plots(flux, err, xjd, name, block_exp_t, block_ind_bound, 
        comp_name="mean", binning=150, norm_flux_lower=0, norm_flux_upper=99,
        plot_lower=None, plot_upper=None, xjd_oot_l=99, xjd_oot_u=99): 
    '''Main fuction to perform the plotting of the lightcurves. Takes in
    a flux and jd array as well as some parameters for the binning and 
    clipping to be performed on the lightcurve. A comparison star name
    is passed in as well. '''

    #Copy data to prevent overwriting input arrays
    plot_flux = np.copy(flux)
    plot_err = np.copy(err)
    plot_xjd = np.copy(xjd)

    #Check sizes are the same
    assert(plot_flux.shape == plot_xjd.shape)
    assert(plot_err.shape == plot_xjd.shape)

    #Remove offset from xjd
    off = np.floor(np.min(plot_xjd))
    xjd_o = plot_xjd - off
    xjd_oot_l -= off
    xjd_oot_u -= off
    
    #Airmass correct flux
    #plot_flux = air_corr(plot_flux, xjd_o, xjd_oot_l, xjd_oot_u)

    #Save data to FITS file
    save_data_fits_err(plot_xjd, plot_flux, plot_err, name, comp_name)
    
    #Clip outliers
    plot_flux[(plot_flux > norm_flux_upper) | (plot_flux < norm_flux_lower)] = np.nan

    #Get finite data mask
    mask = np.isfinite(plot_flux)

    #bin data
    flux_bin = bin_to_size(plot_flux, binning, block_exp_t, block_ind_bound, mask)
    xjd_bin = bin_to_size(xjd_o, binning, block_exp_t, block_ind_bound, mask)

    #Save binned data to FITS file
    save_data_fits(xjd_bin+off, flux_bin, name, comp_name + "_bin")

    #Set up plot
    plt.cla()
    plt.figure(figsize=(8,6), dpi=100)
    
    #Plot unbinned data
    plt.scatter(xjd_o, plot_flux, alpha=0.5, zorder=1, c='b')
    
    #Plot binned data
    plt.scatter(xjd_bin, flux_bin, zorder=2, c='r')

    #Plot expected ingress/egress
    if xjd_oot_l is not 99:
        plt.axvline(x=xjd_oot_l, c='g')
    if xjd_oot_u is not 99:
        plt.axvline(x=xjd_oot_u, c='g')

    #Labels, titles and scaling
    oot_mask = ((xjd_bin < xjd_oot_l) | (xjd_bin > xjd_oot_u))
    frms = (np.nanstd(flux_bin[oot_mask], ddof=1) /
        np.nanmedian(flux_bin[oot_mask]))
    plt.title(name + ', FRMS: %7.5f' % frms)
    plt.xlabel('BJD - %d' %off)
    plt.ylabel('Relative flux')
    
    if (plot_upper is None) and (plot_lower is None):
        plt.autoscale(enable=True, axis='y')
    else:
        plt.ylim((plot_lower, plot_upper))

    #Save plot as png
    png_name = join(dir_,"SAAO_"+name + '_%s.png' % comp_name) 
    plt.savefig(png_name, bbox_inches="tight")
    plt.close()

def save_data_fits(xjd, flux, err, file_name, comp_name):
    '''Function to save the data as a fits file usings the astropy.io.fits
    library a.k.a PyFits.'''

    #Save data as FITS
    t_out = Table([xjd, flux, err], names=('BJD', 'Relative flux', 'Err'))
    fits_name = join(dir_, "SAAO_"+ file_name + '_%s.fits' % comp_name) 
    t_out.write(fits_name, overwrite=True)

def differential_photometry(i_flux, i_err, obj_index, comp_index, norm_mask):

    #Copy data to prevent overwriting of input arrays
    in_flux = np.copy(i_flux)
    in_err = np.copy(i_err)
   
    #create variables to store the comparison star flux and flux err
    comp_flux = np.zeros((in_flux.shape[0], in_flux.shape[2], in_flux.shape[3]))
    comp_flux_err = np.zeros((in_err.shape[0], in_err.shape[2], in_err.shape[3]))

    #Make 0s nans so as not to bias calculations
    in_flux[in_flux == 0] = np.nan
    in_err[in_err == 0] = np.nan
   
    #Get normalised object flux and error
    obj_flux = in_flux[:, obj_index, :, :]
    obj_flux_err = in_err[:, obj_index, :, :]
    '''obj_norm = (np.nanmedian((obj_flux[:, :, norm_mask]), 
                axis=2).reshape((in_flux.shape[0], in_flux.shape[2], 1)))'''
    
    #Get normalised comparison flux and error
    comp_flux_raw = in_flux[:, comp_index, :, :]
    comp_flux_err_raw = in_err[:, comp_index, :, :]
    nan_mask = np.logical_or(np.isnan(comp_flux_raw),
            np.isnan(comp_flux_err_raw))
    comp_flux = np.ma.masked_array(comp_flux_raw, mask=nan_mask)
    comp_flux_err = np.ma.masked_array(comp_flux_err_raw, mask=nan_mask)
    comp_flux = np.average(comp_flux, weights=1/(comp_flux_err**2), axis=1)
    comp_flux_err = np.sqrt(1/np.sum(1/(comp_flux_err**2), axis=1))
    '''comp_norm = (np.nanmedian(comp_flux[:, :, norm_mask], 
            axis=2).reshape((comp_flux.shape[0], comp_flux.shape[1], 1)))'''

    #Get differential flux and error
    diff_flux = obj_flux / comp_flux
    diff_flux_err = diff_flux * np.sqrt((obj_flux_err/obj_flux)**2 +
                (comp_flux_err/comp_flux)**2)
    diff_norm = (np.nanmedian(diff_flux[:, :, norm_mask], 
            axis=2).reshape((diff_flux.shape[0], diff_flux.shape[1], 1)))
    diff_flux /= diff_norm
    diff_flux_err /= diff_norm 

    return diff_flux, diff_flux_err, obj_flux, comp_flux 

class Logger(object):
    def __init__(self, _dir):
        self._dir = _dir
        self.terminal = sys.stdout
        self.log = open(join(self._dir, "SAAO_phot.log"), "w")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        #this flush method is needed for python 3 compatibility.
        pass


if __name__ == "__main__":

    '''===== START OF INPUT PARAMETERS ======'''
    
    aSpecify input-output directory and input photometry file name
    dir_ = ''
    infile_ = '*_phot.fits'

    #Define target and comparison object numbers (indicies) from field plot
    o_num = 2           # As integer
    c_num = [1, 4]      # As list

    #Define normalised flux limits outside which outliers are clipped
    norm_flux_upper = 1.2
    norm_flux_lower = 0

    #Define plot time format to use
    time = "jd"
    
    #Define time to bin up light curve (seconds)
    b = 10 * 60
   
    #Ingress and egress times [None, value]
    xjd_oot_l_p = None      # predicted
    xjd_oot_u_p = None      # predicted
    xjd_oot_l = None        # actual
    xjd_oot_u = None        # actual

    #Plot ingress/egress markers [True, False]
    plot_oot_l_p = True
    plot_oot_u_p = True

    #Define number of plot panel rows and columns per page
    ncols = 2
    nrows = 3

    '''===== END OF INPUT PARAMETERS ====='''

    
    #Initialise instance of Logger which saves screen prints to .log file 
    sys.stdout = Logger(dir_) 
    
    #Load data from photometry file
    with FITS(glob(join(dir_, infile_))[0]) as f:
        hdr = f[0].read_header()
        flux = f['OBJ_FLUX'][:,:,:,:]
        fluxerr = f['OBJ_FLUX_ERR'][:,:,:,:]
        fluxflags = f['OBJ_FLUX_FLAGS'][:,:,:,:]
        obj_bkg_app_flux = f['OBJ_BKG_APP_FLUX'][:,:,:,:]
        bkg_flux = f['RESIDUAL_BKG_FLUX'][:,:,:]
        ccdx = f['OBJ_CCD_X'][:,:]
        ccdy = f['OBJ_CCD_Y'][:,:]
        fwhm = f['MEAN_OBJ_FWHM'][:,:]
        jd = f['JD'][:]
        hjd = f['HJD'][:]
        bjd = f['BJD'][:]
        frame_shift_x = f['FRAME_SHIFT_X'][:]
        frame_shift_y = f['FRAME_SHIFT_Y'][:]
        exp = f['EXPOSURE_TIME'][:]
        airmass = f['AIRMASS'][:]
        apps = f['VARIABLES_APERTURE_RADII'][:]
        bkgs = f['VARIABLES_BKG_PARAMS'][:]

    #Get preffered plot time format
    if time == "hjd": xjd = hjd
    elif time == "bjd": xjd = bjd
    else: xjd = jd
    
    #Get xjd offset time 
    xjd_off = np.floor(np.nanmin(xjd))

    #Get normalisation mask
    if xjd_oot_l is None: xjd_oot_l = np.nanmin(xjd)
    if xjd_oot_u is None: xjd_oot_u = np.nanmax(xjd)
    oot = (xjd < xjd_oot_l) | (xjd > xjd_oot_u)
    if np.any(oot):
        norm_mask = oot
    else:
        norm_mask = np.ones(xjd.shape[0], dtype=bool)

    #Identify blocks of frames with different exposure times
    uniq, ind, inv = np.unique(exp, return_index=True, return_inverse=True)
    block_exposure_times = uniq[inv]
    block_index_boundaries = ind[inv]
    block_index_boundaries.append(flux.shape[3])
    
    #Find background subtraction parameters with lowest residuals
    print ("Bkg subtraction residual flux for each parameter combination "\
        "summed across frames:")
    print np.sum(bkg_flux, axis=(0,2)
    lowest_bkg = np.where(np.nansum(bkg_flux, axis=(0,2)) == np.nanmin(
        np.nansum(bkg_flux, axis=(0,2))))[0][0]
  
    #Initialise plot


    '''MEAN COMPARISON'''
    #Perform differential photometry using mean comparison star
    diff_flux, diff_flux_err, obj_flux, comp_flux = differential_photometry(flux, 
                                                fluxerr, o_num, c_num, norm_mask)

    #Pick the best signal to noise (from oot region if specified)
    signal = np.nanmean(diff_flux[:,:,norm_mask], axis=2)
    noise = np.nanstd(diff_flux[:,:,norm_mask], axis=2, ddof=1)
    sn_max = (np.where(signal/noise == np.nanmax(signal/noise)))
    sn_max_bkg = (np.where(signal/noise == np.nanmax((signal/noise)[:,lowest_bkg])))
    sn_max_a, sn_max_b = get_sn_max(sn_max)
    sn_max_bkg_a, sn_max_bkg_b = get_sn_max(sn_max_bkg)

    #Print signal to noise
    print ("Max S/N overall is {:.2f} using aperture "\
            "rad {:.1f} pix and bkg params {}".format(np.nanmax((signal/noise)[:,:]),
            apps[sn_max_a], bkgs[sn_max_b]))
    print ("Max S/N with lowest bkg residuals is "\
            "{:.2f} using aperture rad {:.1f} pix and bkg params {}".format(
        np.nanmax((signal/noise)[:,lowest_bkg]),apps[sn_max_bkg_a],bkgs[sn_max_bkg_b]))
   
    #Make plots using mean of all comparison stars
    make_lc_plots(diff_flux[sn_max_bkg_a,sn_max_bkg_b],
            diff_flux_err[sn_max_bkg_a,sn_max_bkg_b], xjd, name, block_exposure_times,
            block_index_boundaries, comp_name="comparison_mean", binning=b, 
            norm_flux_lower=norm_flux_lower, norm_flux_upper=norm_flux_upper,
            xjd_oot_l=xjd_oot_l, xjd_oot_u=xjd_oot_u)
    print "Mean plot finished."

    '''TARGET BY ITSELF'''
    #Calculate signal to noise (from oot region if specified)
    signal = np.nanmean(flux[:,o_num,:,:][:,:,norm_mask], axis=2)
    noise = np.nanstd(flux[:,o_num,:,:][:,:,norm_mask], axis=2, ddof=1)
    sn_max_bkg = (np.where(signal/noise == np.nanmax((signal/noise)[:,lowest_bkg])))
    sn_max_bkg_a, sn_max_bkg_b = get_sn_max(sn_max_bkg)
    print ("Max S/N with lowest bkg residuals is "\
            "{:.2f} using aperture rad {:.1f} pix and bkg params {}".format(
        np.nanmax((signal/noise)[:,lowest_bkg]),apps[sn_max_bkg_a],bkgs[sn_max_bkg_b]))

    #Get normalised flux of target by itself
    flux_target_solo = flux[:,o_num,:,:][sn_max_bkg_a,:,:][sn_max_bkg_b,:]
    flux_target_solo_err = fluxerr[:,o_num,:,:][sn_max_bkg_a,:,:][sn_max_bkg_b,:]
    flux_target_solo_err /= np.nanmedian(flux_target_solo[norm_mask])
    flux_target_solo /= np.nanmedian(flux_target_solo[norm_mask])
    
    #Plot flux of target star by itself
    make_lc_plots(flux_target_solo, flux_target_solo_err, xjd, name, 
            block_exposure_times, block_index_boundaries, 
            comp_name="target_by_itself", binning=b, 
            xjd_oot_l=xjd_oot_l, xjd_oot_u=xjd_oot_u)
    print "Plot of target by itself is finished."
    
    '''COMPARISONS BY THEMSELVES'''
    #Work through the individual comparison stars
    for cindex in c_num:
        
        #Calculate signal to noise (from oot region if specified)
        signal = np.nanmean(flux[:,cindex,:,:][:,:,norm_mask], axis=2)
        noise = np.nanstd(flux[:,cindex,:,:][:,:,norm_mask], axis=2, ddof=1)
        #sn_max = (np.where(signal/noise == np.nanmax(signal/noise)))
        #sn_max_a, sn_max_b = get_sn_max(sn_max)
        sn_max_bkg = (np.where(signal/noise == np.nanmax((signal/noise)[:,lowest_bkg])))
        sn_max_bkg_a, sn_max_bkg_b = get_sn_max(sn_max_bkg)
        print ("Max S/N with lowest bkg residuals is "\
            "{:.2f} using aperture rad {:.1f} pix and bkg params {}".format(
        np.nanmax((signal/noise)[:,lowest_bkg]),apps[sn_max_bkg_a],bkgs[sn_max_bkg_b]))

        #Get normalised flux of comparison by itself
        flux_comp_solo = flux[:,cindex,:,:][sn_max_bkg_a,:,:][sn_max_bkg_b,:]
        flux_comp_solo_err = fluxerr[:,cindex,:,:][sn_max_bkg_a,:,:][sn_max_bkg_b,:]
        flux_comp_solo_err /= np.nanmedian(flux_comp_solo[norm_mask])
        flux_comp_solo /= np.nanmedian(flux_comp_solo[norm_mask])
        
        #Plot flux of comparison star by itself
        make_lc_plots(flux_comp_solo, flux_comp_solo_err, xjd, name, 
                block_exposure_times,
                block_index_boundaries, comp_name="comparison_"+str(cindex)+"_by_itself", 
                binning=b, xjd_oot_l=xjd_oot_l, xjd_oot_u=xjd_oot_u)
        print "Plot of comp star %i by itself is finished." % cindex

        '''TARGET VS INDIVIDUAL COMPARISONS'''
        #Get differential flux of object with comparison star
        diff_flux, diff_flux_err, obj_flux, comp_flux = differential_photometry(flux, 
                                            fluxerr, o_num, [cindex], norm_mask)
        signal = np.nanmean(diff_flux[:,:,norm_mask], axis=2)
        noise = np.nanstd(diff_flux[:,:,norm_mask], axis=2, ddof=1)
        sn_max = np.where(signal/noise == np.nanmax(signal/noise))
        sn_max_a, sn_max_b = get_sn_max(sn_max)
        sn_max_bkg = (np.where(signal/noise == np.nanmax((signal/noise)[:,lowest_bkg])))
        sn_max_bkg_a, sn_max_bkg_b = get_sn_max(sn_max_bkg)
        print ("Max S/N with lowest bkg residuals is "\
            "{:.2f} using aperture rad {:.1f} pix and bkg params {}".format(
        np.nanmax((signal/noise)[:,lowest_bkg]),apps[sn_max_bkg_a],bkgs[sn_max_bkg_b]))

        #Plot differential flux of object with comparison star
        make_lc_plots(diff_flux[sn_max_bkg_a,sn_max_bkg_b],
                diff_flux_err[sn_max_bkg_a,sn_max_bkg_b], xjd, name, 
                block_exposure_times,block_index_boundaries, 
                comp_name="comparison_"+str(cindex), binning=b, 
                norm_flux_lower=norm_flux_lower,
                norm_flux_upper=norm_flux_upper,
                xjd_oot_l=xjd_oot_l,xjd_oot_u=xjd_oot_u)
        print "Comparison plot for comp star %i is finished." % cindex
        
        '''EACH COMPARISON VS MEAN OF OTHER COMPARISONS'''
        #Get diff flux of comparison with mean of other comparisons
        if (len(c_num) > 1):
            comp_mask = np.not_equal(c_num, [cindex]*len(c_num))
            other_comps = np.asarray(c_num)[comp_mask]
            (diff_flux_other, diff_flux_other_err, obj_flux_other,
                comp_flux_other) = differential_photometry(
                                flux, fluxerr, cindex, other_comps, norm_mask)
            
            #Get signal to noise (from oot region if specified)
            signal = np.nanmean(diff_flux_other[:,:,norm_mask], axis=2) 
            noise = np.nanstd(diff_flux_other[:,:,norm_mask], axis=2, ddof=1)  
            sn_max_bkg = (np.where(signal/noise == 
                                        np.nanmax((signal/noise)[:,lowest_bkg])))
            sn_max_bkg_a, sn_max_bkg_b = get_sn_max(sn_max_bkg)
            print ("Max S/N with lowest bkg residuals is "\
            "{:.2f} using aperture rad {:.1f} pix and bkg params {}".format(
            np.nanmax((signal/noise)[:,lowest_bkg]),apps[sn_max_bkg_a],bkgs[sn_max_bkg_b]))

            #Plot differential flux
            make_lc_plots(diff_flux_other[sn_max_bkg_a,sn_max_bkg_b],
                    diff_flux_other_err[sn_max_bkg_a,sn_max_bkg_b], xjd, name, 
                    block_exposure_times, block_index_boundaries, 
                comp_name="comparison_"+str(cindex)+"_vs_other_comps", 
                binning=b, norm_flux_lower=norm_flux_lower,
                norm_flux_upper=norm_flux_upper,
                xjd_oot_l=xjd_oot_l, xjd_oot_u=xjd_oot_u)
            print ("Comparison plot of comp star %i vs mean of other comparisons"\
                     " is finished." % cindex)
