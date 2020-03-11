import numpy as np
import tensorflow as tf
import pandas as pd
import optparse
from tensorflow.python.client import device_lib
from tensorflow import keras as kr
import os
import matplotlib.pyplot as plt

import numba
import json

from qDenseCNN import qDenseCNN

#for earth movers distance calculation
import ot

@numba.jit
def normalize(data,rescaleInputToMax=False):
    norm =[]
    for i in range(len(data)):
        if rescaleInputToMax:
            norm.append( data[i].max() )
            data[i] = 1.*data[i]/data[i].max()
        else:
            norm.append( data[i].sum() )
            data[i] = 1.*data[i]/data[i].sum()
    return data,np.array(norm)

def split(shaped_data, validation_frac=0.2):
  N = round(len(shaped_data)*validation_frac)
  
  #randomly select 25% entries
  index = np.random.choice(shaped_data.shape[0], N, replace=False)  
  #select the indices of the other 75%
  full_index = np.array(range(0,len(shaped_data)))
  train_index = np.logical_not(np.in1d(full_index,index))
  
  val_input = shaped_data[index]
  train_input = shaped_data[train_index]

  print(train_input.shape)
  print(val_input.shape)

  return val_input,train_input

def train(autoencoder,encoder,train_input,val_input,name,n_epochs=100):

  es = kr.callbacks.EarlyStopping(monitor='val_loss', mode='min', verbose=1, patience=3)
  history = autoencoder.fit(train_input,train_input,
                epochs=n_epochs,
                batch_size=500,
                shuffle=True,
                validation_data=(val_input,val_input),
                callbacks=[es]
                )

  plt.plot(history.history['loss'])
  plt.plot(history.history['val_loss'])
  plt.title('Model loss %s'%name)
  plt.ylabel('Loss')
  plt.xlabel('Epoch')
  plt.legend(['Train', 'Test'], loc='upper right')
  plt.savefig("history_%s.png"%name)
  #plt.show()

  save_models(autoencoder,name)

  return history

def save_models(autoencoder, name):
  json_string = autoencoder.to_json()
  with open('./%s.json'%name,'w') as f:
      f.write(json_string)
  encoder = autoencoder.get_layer("encoder")
  json_string = encoder.to_json()
  with open('./%s.json'%("encoder_"+name),'w') as f:
      f.write(json_string)
  decoder = autoencoder.get_layer("decoder")
  json_string = decoder.to_json()
  with open('./%s.json'%("decoder_"+name),'w') as f:
      f.write(json_string)
  autoencoder.save_weights('%s.hdf5'%name)
  encoder.save_weights('%s.hdf5'%("encoder_"+name))
  decoder.save_weights('%s.hdf5'%("decoder_"+name))
  return
  

def predict(x,autoencoder,encoder,reshape=True):
  decoded_Q = autoencoder.predict(x)
  encoded_Q = encoder.predict(x)
 
  #need reshape for CNN layers  
  if reshape :
    decoded_Q = np.reshape(decoded_Q,(len(decoded_Q),12,4))
    encoded_shape = encoded_Q.shape
    encoded_Q = np.reshape(encoded_Q,(len(encoded_Q),encoded_shape[3],encoded_shape[1]))
  return decoded_Q, encoded_Q

### cross correlation of input/output 
def cross_corr(x,y):
    cov = np.cov(x.flatten(),y.flatten())
    std = np.sqrt(np.diag(cov)+1e-10)
    #std = np.sqrt(np.diag(cov)+(1e-10 * np.ones_like(cov)))
    corr = cov / np.multiply.outer(std, std)
    return corr[0,1]

def ssd(x,y):
    ssd=np.sum(((x-y)**2).flatten())
    ssd = ssd/(np.sum(x**2)*np.sum(y**2))**0.5
    return ssd

def GetHexCoords():
    return np.array([ 
        [0.0, 0.0], [0.0, -2.4168015], [0.0, -4.833603], [0.0, -7.2504044], 
        [2.09301, -1.2083969], [2.09301, -3.6251984], [2.09301, -6.042], [2.09301, -8.458794], 
        [4.18602, -2.4168015], [4.18602, -4.833603], [4.18602, -7.2504044], [4.18602, -9.667198], 
        [6.27903, -3.6251984], [6.27903, -6.042], [6.27903, -8.458794], [6.27903, -10.875603], 
        [-8.37204, -10.271393], [-6.27903, -9.063004], [-4.18602, -7.854599], [-2.0930138, -6.6461945], 
        [-8.37204, -7.854599], [-6.27903, -6.6461945], [-4.18602, -5.4377975], [-2.0930138, -4.229393], 
        [-8.37204, -5.4377975], [-6.27903, -4.229393], [-4.18602, -3.020996], [-2.0930138, -1.8125992], 
        [-8.37204, -3.020996], [-6.27903, -1.8125992], [-4.18602, -0.6042023], [-2.0930138, 0.6042023], 
        [4.7092705, -12.386101], [2.6162605, -11.177696], [0.5232506, -9.969299], [-1.5697594, -8.760895], 
        [2.6162605, -13.594498], [0.5232506, -12.386101], [-1.5697594, -11.177696], [-3.6627693, -9.969299], 
        [0.5232506, -14.802895], [-1.5697594, -13.594498], [-3.6627693, -12.386101], [-5.7557793, -11.177696], 
        [-1.5697594, -16.0113], [-3.6627693, -14.802895], [-5.7557793, -13.594498], [-7.848793, -12.386101]
    ])

# calculate "earth mover's distance"
# (cost, in distance, to move earth from one config to another)
hexCoords = GetHexCoords()
hexMetric = ot.dist(hexCoords, hexCoords, 'euclidean')
def emd(_x, _y, threshold=-1):    
    x = np.array(_x, dtype=np.float64)
    y = np.array(_y, dtype=np.float64)
    x = 1./x.sum()*x.flatten()
    y = 1./y.sum()*y.flatten()

    if threshold > 0:
        # only keep entries above 2%, e.g.
        x = np.where(x>threshold,x,0)
        y = np.where(y>threshold,y,0)
        x = 1.*x/x.sum()
        y = 1.*y/y.sum()

    return ot.emd2(x, y, hexMetric)

def visualize(input_Q,decoded_Q,encoded_Q,index,name='model_X'):
  if index.size==0:
    Nevents=8
    #randomly pick Nevents if index is not specified
    index = np.random.choice(input_Q.shape[0], Nevents, replace=False) 
  else:
    Nevents = len(index) 
  
  inputImg    = input_Q[index]
  encodedImg  = encoded_Q[index]
  outputImg   = decoded_Q[index]
  
  fig, axs = plt.subplots(3, Nevents, figsize=(16, 10))
  
  for i in range(0,Nevents):
      if i==0:
          axs[0,i].set(xlabel='',ylabel='cell_y',title='Input_%i'%i)
      else:
          axs[0,i].set(xlabel='',title='Input_%i'%i)        
      c1=axs[0,i].imshow(inputImg[i])
 
  for i in range(0,Nevents):
      if i==0:
          axs[1,i].set(xlabel='cell_x',ylabel='cell_y',title='CNN Ouput_%i'%i)        
      else:
          axs[1,i].set(xlabel='cell_x',title='CNN Ouput_%i'%i)
      c1=axs[1,i].imshow(outputImg[i])
     
  for i in range(0,Nevents):
    if i==0:
        axs[2,i].set(xlabel='latent dim',ylabel='depth',title='Encoded_%i'%i)
    else:
        axs[2,i].set(xlabel='latent dim',title='Encoded_%i'%i)
    c1=axs[2,i].imshow(encodedImg[i])
    plt.colorbar(c1,ax=axs[2,i])
  
  plt.tight_layout()
  plt.savefig("%s_examples.png"%name)
 
def visMetric(input_Q,decoded_Q,maxQ,name, skipPlot=False): 
  #plt.show()
  def plothist(y,xlabel,name):
    plt.figure(figsize=(6,4))
    plt.hist(y,50)
    
    mu = np.mean(y)
    std = np.std(y)
    ax = plt.axes()
    plt.text(0.1, 0.9, name,transform=ax.transAxes)
    plt.text(0.1, 0.8, r'$\mu=%.3f,\ \sigma=%.3f$'%(mu,std),transform=ax.transAxes)
    plt.xlabel(xlabel)
    plt.ylabel('Entry')
    plt.title('%s on validation set'%xlabel)
    plt.savefig("hist_%s.png"%name)


  cross_corr_arr = np.array([cross_corr(input_Q[i],decoded_Q[i]) for i in range(0,len(decoded_Q))]  )
  ssd_arr        = np.array([ssd(decoded_Q[i],input_Q[i]) for i in range(0,len(decoded_Q))])
  emd_arr        = np.array([emd(decoded_Q[i],input_Q[i]) for i in range(0,len(decoded_Q))])

  if skipPlot: return cross_corr_arr,ssd_arr,emd_arr

  plothist(cross_corr_arr,'cross correlation',name+"_corr")
  plothist(ssd_arr,'sum squared difference',name+"_ssd")
  plothist(emd_arr,'earth movers distance',name+"_emd")

  plt.figure(figsize=(6,4))
  plt.hist([input_Q.flatten(),decoded_Q.flatten()],20,label=['input','output'])
  plt.yscale('log')
  plt.legend(loc='upper right')
  plt.xlabel('Charge fraction')
  plt.savefig("hist_Qfr_%s.png"%name)

  input_Q_abs   = np.array([input_Q[i] * maxQ[i] for i in range(0,len(input_Q))])
  decoded_Q_abs = np.array([decoded_Q[i]*maxQ[i] for i in range(0,len(decoded_Q))])

  plt.figure(figsize=(6,4))
  plt.hist([input_Q_abs.flatten(),decoded_Q_abs.flatten()],20,label=['input','output'])
  plt.yscale('log')
  plt.legend(loc='upper right')
  plt.xlabel('Charge')
  plt.savefig("hist_Qabs_%s.png"%name)

  nonzeroQs = np.count_nonzero(input_Q_abs.reshape(len(input_Q_abs),48),axis=1)
  occbins = [0,5,10,20,48]
  fig, axes = plt.subplots(1,len(occbins)-1, figsize=(16, 4))
  for i,ax in enumerate(axes):
      #print(cross_corr_arr[selection])
      selection=np.logical_and(nonzeroQs<occbins[i+1],nonzeroQs>occbins[i])
      label = '%i<occ<%i'%(occbins[i],occbins[i+1])
      mu = np.mean(cross_corr_arr[selection])
      std = np.std(cross_corr_arr[selection])
      plt.text(0.1, 0.8, r'$\mu=%.3f,\ \sigma=%.3f$'%(mu,std),transform=ax.transAxes)
      ax.hist(cross_corr_arr[selection],40)
      ax.set(xlabel='corr',title=label)
  plt.tight_layout()
  #plt.show()
  plt.savefig('corr_vs_occ_%s.png'%name)

  return cross_corr_arr,ssd_arr,emd_arr

def GetBitsString(In, Accum, Weight):
    s=""
    s += "Input{}b{}i".format(In['total'],In['integer'])
    s += "_Accum{}b{}i".format(Accum['total'],Accum['integer'])
    s += "_Weight{}b{}i".format(Weight['total'],Weight['integer'])
    return s

def trainCNN(options,args, incr):

  # List devices:
  print(device_lib.list_local_devices())
  print("Num GPUs Available: ", len(tf.config.experimental.list_physical_devices('GPU')))
  print("Is GPU available? ", tf.test.is_gpu_available())

  # generic precisions
  nb = 4+incr*2
  print('training with',nb,'input total bits')
  nBits_input  = {'total': nb, 'integer': 2}
  #nBits_input  = {'total': 16, 'integer': 6}
  nBits_accum  = {'total': 16, 'integer': 6}
  nBits_weight = {'total': 16, 'integer': 6}
  nBits_encod  = {'total': 16,  'integer': 6}
  # nBits_input  = {'total': 32, 'integer': 8}
  # nBits_accum  = {'total': 32, 'integer': 8}
  # nBits_weight = {'total': 32, 'integer': 8}
  # nBits_encod  = {'total': 6,  'integer': 2}
  # model-dependent -- use common weights unless overridden
  conv_qbits = nBits_weight
  dense_qbits = nBits_weight


  # from tensorflow.keras import backend
  # backend.set_image_data_format('channels_first')

  data = pd.read_csv(options.inputFile,dtype=np.float64)  ## big  300k file
  normdata,maxdata = normalize(data.values.copy(),rescaleInputToMax=options.rescaleInputToMax)

  arrange8x8 = np.array([
              28,29,30,31,0,4,8,12,
              24,25,26,27,1,5,9,13,
              20,21,22,23,2,6,10,14,
              16,17,18,19,3,7,11,15,
              47,43,39,35,35,34,33,32,
              46,42,38,34,39,38,37,36,
              45,41,37,33,43,42,41,40,
              44,40,36,32,47,46,45,44])
  
  arrMask  =  np.array([
              1,1,1,1,1,1,1,1,
              1,1,1,1,1,1,1,1,
              1,1,1,1,1,1,1,1,
              1,1,1,1,1,1,1,1,
              1,1,1,1,1,1,1,1,
              1,1,1,0,0,1,1,1,
              1,1,0,0,0,0,0,1,
              1,0,0,0,0,0,0,1,])

  arrange443 = np.array([0,16, 32,
                         1,17, 33,
                         2,18, 34,
                         3,19, 35,
                         4,20, 36,
                         5,21, 37,
                         6,22, 38,
                         7,23, 39,
                         8,24, 40,
                         9,25, 41,
                        10,26, 42,
                        11,27, 43,
                        12,28, 44,
                        13,29, 45,
                        14,30, 46,
                        15,31, 47])

  models = [
    #{'name':'denseCNN',  'ws':'denseCNN.hdf5', 'pams':{'shape':(1,8,8) } },
    #{'name':'denseCNN_2',  'ws':'denseCNN_2.hdf5',
    #  'pams':{'shape':(8,8,1) ,'arrange': arrange8x8,'arrMask':arrMask  } },

    #{'name':'8x8_nomask','ws':'','pams':{'shape':(8,8,1) ,'arrange': arrange8x8  }},
    #{'name':'nfil4','ws':'','pams':{'shape':(8,8,1) ,'arrange': arrange8x8,'arrMask':arrMask,  'CNN_layer_nodes':[4]}},
    #{'name':'nfils_842','ws':'nfils_842.hdf5','pams':{'shape':(8,8,1) ,'arrange': arrange8x8,'arrMask':arrMask,
    #        'CNN_layer_nodes':[8,4,2],
    #        'CNN_kernel_size':[3,3,3],
    #        'CNN_pool':[False,False,False],
    #}} ,
    #{'name':'nfils_842_pool2','ws':'','pams':{'shape':(8,8,1) ,'arrange': arrange8x8,'arrMask':arrMask,
    #        'CNN_layer_nodes':[8,4,2],
    #        'CNN_kernel_size':[3,3,3],
    #        'CNN_pool':[False,True,False],
    #}} ,
    #{'name':'8x8_dim10','ws':'','vis_shape':(8,8),'pams':{'shape':(8,8,1) ,'arrange': arrange8x8,'arrMask':arrMask,  'encoded_dim':10}},
    #{'name':'8x8_dim8','ws':'','pams':{'shape':(8,8,1) ,'arrange': arrange8x8,'arrMask':arrMask,  'encoded_dim':8}},
    #{'name':'8x8_dim4','ws':'','pams':{'shape':(8,8,1) ,'arrange': arrange8x8,'arrMask':arrMask,  'encoded_dim':4}},
    #{'name':'12x4_norm','ws':'','vis_shape':(12,4),'pams':{'shape':(12,4,1),
    #        'CNN_layer_nodes':[8,4,4,2],
    #        'CNN_kernel_size':[3,3,3,3],
    #        'CNN_pool':[False,False,False,False],
    #}},

    #{'name':'4x4_norm'    ,'ws':'4x4_norm.hdf5'    ,'pams':{'shape':(3,4,4) ,'channels_first':True }},
    #{'name':'4x4_norm_d10','ws':'4x4_norm_d10.hdf5','pams':{'shape':(3,4,4) ,'channels_first':False ,
     #                                                       'encoded_dim':10, 'qbits':qBitStr}},
    {'name': '4x4_norm_d10', 'ws': '',
       'pams': {'shape': (4, 4, 3), 'channels_first': False, 'arrange': arrange443, 'encoded_dim': 10,
                'loss': 'weightedMSE', 'nBits_weight':nBits_weight, 'nBits_input':nBits_input, 'nBits_accum':nBits_accum, 'nBits_encod': nBits_encod}},
    #{'name':'4x4_norm_d8' ,'ws':'4x4_norm_d8.hdf5' ,'pams':{'shape':(3,4,4) ,'channels_first':True ,'encoded_dim':8}},

    #{'name':'4x4_v1',  'ws':'','vis_shape':(4,12),'pams':{'shape':(3,4,4) ,'channels_first':True,
    #     'CNN_layer_nodes':[8,8],
    #     'CNN_kernel_size':[3,3],
    #     'CNN_pool':[False,False],
    #}},
    #{'name':'4x4_v2',  'ws':'','vis_shape':(4,12),'pams':{'shape':(3,4,4) ,'channels_first':True,
    #     'CNN_layer_nodes':[8,8],
    #     'CNN_kernel_size':[3,3],
    #     'CNN_pool':[False,False],
    #     'Dense_layer_nodes':[16],
    #}},
    #{'name':'4x4_v3' ,'ws':'4x4_v3.hdf5','pams':{'shape':(3,4,4) ,'channels_first':True ,'CNN_kernel_size':[2]}},
    #{'name':'4x4_norm_v4','ws':'4x4_norm_v4.hdf5','pams':{'shape':(3,4,4) ,'channels_first':True,
    #     'CNN_layer_nodes':[4,4,4],
    #     'CNN_kernel_size':[3,3,3],
    #     'CNN_pool':[False,False,False],
    #}},
    #{'name':'4x4_norm_v5','ws':'4x4_norm_v5.hdf5','pams':{'shape':(3,4,4) ,'channels_first':True ,
    #     'CNN_layer_nodes':[8,4,2],
    #     'CNN_kernel_size':[3,3,3],
    #     'CNN_pool':[False,False,False],
    #}},
    #{'name':'4x4_norm_v6','ws':'4x4_norm_v6.hdf5','pams':{'shape':(3,4,4) ,'channels_first':True ,
    #     'CNN_layer_nodes':[8,4,2],
    #     'CNN_kernel_size':[5,5,3],
    #     'CNN_pool':[False,False,False],
    #}},
    #{'name':'4x4_norm_v7','ws':'4x4_norm_v7.hdf5','pams':{'shape':(3,4,4) ,'channels_first':True,
    #     'CNN_layer_nodes':[4,4,4],
    #     'CNN_kernel_size':[5,5,3],
    #     'CNN_pool':[False,False,False],
    #}},
    #{'name':'4x4_norm_v8','ws':'','pams':{'shape':(4,4,3) ,'channels_first':False,'arrange':arrange443,
    #     'CNN_layer_nodes':[8,4,4,4,2],
    #     'CNN_kernel_size':[3,3,3,3,3],
    #     'CNN_pool':[0,0,0,0,0],
    #}},
    #{'name':'4x4_norm_v8_clone10','ws':'','pams':{'shape':(3,4,4) ,'channels_first':True,
    #     'CNN_layer_nodes':[8,4,4,4,2],
    #     'CNN_kernel_size':[3,3,3,3,3],
    #     'CNN_pool':[0,0,0,0,0],
    #     'n_copy':10,'occ_low':20,'occ_hi':48,
    #}},
    #{'name':'4x4_norm_v8_wmse','ws':'4x4_norm_v8_wmse.hdf5','pams':{'shape':(3,4,4) ,'channels_first':True,
    #     'CNN_layer_nodes':[8,4,4,4,2],
    #     'CNN_kernel_size':[3,3,3,3,3],
    #     'CNN_pool':[0,0,0,0,0],
    #     'loss':'weightedMSE'
    #}},
    #{'name':'4x4_norm_v8_KL','ws':'','pams':{'shape':(3,4,4) ,'channels_first':True,
    #     'CNN_layer_nodes':[8,4,4,4,2],
    #     'CNN_kernel_size':[3,3,3,3,3],
    #     'CNN_pool':[0,0,0,0,0],
    #     'loss':'kullback_leibler_divergence'
    #}},
    #{'name':'4x4_norm_v8_skimOcc','ws':'','pams':{'shape':(3,4,4) ,'channels_first':True,
    #     'CNN_layer_nodes':[8,4,4,4,2],
    #     'CNN_kernel_size':[3,3,3,3,3],
    #     'CNN_pool':[0,0,0,0,0],
    #     'skimOcc':True,'occ_low':20,'occ_hi':48,
    #}},
    #{'name':'4x4_norm_v8_hinge','ws':'','pams':{'shape':(3,4,4) ,'channels_first':True,
    #     'CNN_layer_nodes':[8,4,4,4,2],
    #     'CNN_kernel_size':[3,3,3,3,3],
    #     'CNN_pool':[0,0,0,0,0],
    #     'loss':losses.hinge
    #}},

  ]

  summary = pd.DataFrame(columns=['name','en_pams','tot_pams','corr','ssd','emd'])
  #os.chdir('./CNN/')
  #os.chdir('./12x4/')
  os.chdir(options.odir)
  for model in models:
    model_name = model['name'] + "_" + GetBitsString(nBits_input,nBits_accum,nBits_weight)
    if not os.path.exists(model_name):
      os.mkdir(model_name)
    os.chdir(model_name)

    m = qDenseCNN(weights_f=model['ws'])
    m.setpams(model['pams'])
    m.init()
    shaped_data                = m.prepInput(normdata)
    val_input, train_input     = split(shaped_data)
    m_autoCNN , m_autoCNNen    = m.get_models()
    if model['ws']=='':
      history = train(m_autoCNN,m_autoCNNen,train_input,val_input,name=model_name,n_epochs = options.epochs)
    else:
      save_models(m_autoCNN,model_name)

    Nevents = 8
    N_verify = 50

    input_Q,cnn_deQ ,cnn_enQ   = m.predict(val_input)
    
    ## csv files for RTL verification
    N_csv= (options.nCSV if options.nCSV>=0 else input_Q.shape[0]) # about 80k
    np.savetxt("verify_input.csv", input_Q[0:N_csv].reshape(N_csv,48), delimiter=",",fmt='%.12f')
    np.savetxt("verify_output.csv",cnn_enQ[0:N_csv].reshape(N_csv,m.pams['encoded_dim']), delimiter=",",fmt='%.12f')
    np.savetxt("verify_decoded.csv",cnn_deQ[0:N_csv].reshape(N_csv,48), delimiter=",",fmt='%.12f')

    index = np.random.choice(input_Q.shape[0], Nevents, replace=False)
    corr_arr, ssd_arr, emd_arr  = visMetric(input_Q,cnn_deQ,maxdata,name=model_name, skipPlot=options.skipPlot)

    if not options.skipPlot:
        hi_corr_index = (np.where(corr_arr>0.9))[0]
        low_corr_index = (np.where(corr_arr<0.2))[0]
        visualize(input_Q,cnn_deQ,cnn_enQ,index,name=model_name)
        if len(hi_corr_index)>0:
            index = np.random.choice(hi_corr_index, min(Nevents,len(hi_corr_index)), replace=False)  
            visualize(input_Q,cnn_deQ,cnn_enQ,index,name=model_name+"_corr0.9")
        
        if len(low_corr_index)>0:
            index = np.random.choice(low_corr_index,min(Nevents,len(low_corr_index)), replace=False)  
            visualize(input_Q,cnn_deQ,cnn_enQ,index,name=model_name+"_corr0.2")

    model['corr'] = np.round(np.mean(corr_arr),3)
    model['ssd'] = np.round(np.mean(ssd_arr),3)
    model['emd'] = np.round(np.mean(emd_arr),3)

    summary = summary.append({'name':model_name,
                              'corr':model['corr'],
                              'ssd':model['ssd'],
                              'emd':model['emd'],
                              'en_pams' : m_autoCNNen.count_params(),
                              'tot_pams': m_autoCNN.count_params(),
                              },ignore_index=True)

    #print('CNN ssd: ' ,np.round(SSD(input_Q,cnn_deQ),3))
    with open(model_name+"_pams.json",'w') as f:
        f.write(json.dumps(m.get_pams(),indent=4))

    os.chdir('../')
  os.chdir('../')
  print(summary)
  return summary


if __name__== "__main__":

    parser = optparse.OptionParser()
    parser.add_option('-o',"--odir", type="string", default = 'CNN/',dest="odir", help="input TSG ntuple")
    parser.add_option('-i',"--inputFile", type="string", default = 'CALQ_output_10x.csv',dest="inputFile", help="input TSG ntuple")
    parser.add_option("--dryRun", action='store_true', default = False,dest="dryRun", help="dryRun")
    parser.add_option("--epochs", type='int', default = 100, dest="epochs", help="n epoch to train")
    parser.add_option("--skipPlot", action='store_true', default = False,dest="skipPlot", help="skip the plotting step")
    parser.add_option("--nCSV", type='int', default = 50, dest="nCSV", help="n of validation events to write to csv")
    parser.add_option("--rescaleInputToMax", action='store_true', default = False,dest="rescaleInputToMax", help="recale the input images so the maximum deposit is 1. Else normalize")
    (options, args) = parser.parse_args()
    #trainCNN(options,args)


    emd_arr = []
    bits_arr = []

    for i in range(10):
        model_info = trainCNN(options,args,i)
        bits_arr.append(4+i*2)
        emd_arr.append(model_info['emd'])
    print(bits_arr,emd_arr)
    plt.plot(bits_arr,emd_arr)
    plt.title('Scan')
    plt.ylabel('EMD')
    plt.xlabel('n bits')
    plt.legend(['others 16,6'], loc='upper right')

    plt.savefig("emd_vs_bits_input.png")
