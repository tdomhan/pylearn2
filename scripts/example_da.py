"""An example of how to use the library so far."""
# Standard library imports
import sys

# Third-party imports
import numpy
import theano
from theano import tensor

try:
    import framework
except ImportError:
    print >>sys.stderr, \
            "Framework couldn't be imported. Make sure you have the " \
            "repository root on your PYTHONPATH (or as your current " \
            "working directory)"
    sys.exit(1)

# Local imports
from framework.cost import MeanSquaredError,CrossEntropy
from framework.corruption import GaussianCorruptor
from framework.autoencoder import DenoisingAutoencoder,build_stacked_ae
from framework.optimizer import SGDOptimizer


if __name__ == "__main__":
    # Simulate some fake data.
    rng = numpy.random.RandomState(seed=42)
    data = numpy.ndarray.astype(rng.normal(size=(500, 15)), numpy.float32)

    conf = {
        'corruption_level': 0.1,
        'nhid': 20,
        'nvis': data.shape[1],
        'anneal_start': 100,
        'base_lr': 0.01, 
        'tied_weights': True, 
        'act_enc': 'tanh',
        'act_dec': None,
        #'lr_hb': 0.10,
        #'lr_vb': 0.10,
        'tied_weights': False ,
        'solution': 'l1_penalty',
        'sparse_penalty': 0.01,
        'sparsityTarget': 0.1 ,
        'sparsityTargetPenalty': 0.001 ,
        'irange': 0.001, 
    }

    # A symbolic input representing your minibatch.
    minibatch = tensor.matrix()

    # Allocate a denoising autoencoder with binomial noise corruption.
    corruptor = GaussianCorruptor(conf['corruption_level'])
    da = DenoisingAutoencoder(corruptor, conf['nvis'], conf['nhid'],
                              conf['act_enc'], conf['act_dec'], conf['tied_weights'], conf['solution'], conf['sparse_penalty'],
                              conf['sparsityTarget'], conf['sparsityTargetPenalty'])

    # Allocate an optimizer, which tells us how to update our model.
    # TODO: build the cost another way
    cost = MeanSquaredError(da)(minibatch, da.reconstruct(minibatch))
    trainer = SGDOptimizer(da, conf['base_lr'], conf['anneal_start'])
    updates = trainer.cost_updates(cost)

    # Finally, build a Theano function out of all this.
    train_fn = theano.function([minibatch], cost, updates=updates)

    # Suppose we want minibatches of size 10
    batchsize = 100

    # Here's a manual training loop. I hope to have some classes that
    # automate this a litle bit.
    for epoch in xrange(2):
        for offset in xrange(0, data.shape[0], batchsize):
            minibatch_err = train_fn(data[offset:(offset + batchsize)])
            print "epoch %d, batch %d-%d: %f" % \
                    (epoch, offset, offset + batchsize - 1, minibatch_err)

    # Suppose you then want to use the representation for something.
    transform = theano.function([minibatch], da([minibatch])[0])

    
    print "Transformed data:"
    
    #print numpy.histogram(transform(data))

    # We'll now create a stacked denoising autoencoder. First, we change
    # the number of hidden units to be a list. This tells the build_stacked_AE
    # method how many layers to make.
    sda_conf = conf.copy()
    sda_conf['nhid'] = [20, 20, 10]
    
    # Add to cost function a regularization term for each layer :
    #	- Layer1 : l1_penalty with sparse_penalty = 0.01
    #	- Layer2 : sqr_penalty with sparsityTarget = 0.2 and sparsityTargetPenalty = 0.01
    #	- Layer3 : l1_penalty with sparse_penalty = 0.1
    
    sda_conf['solution'] = ['l1_penalty','sqr_penalty','l1_penalty']
    sda_conf['sparse_penalty'] = [0.02, 0, 0.1]
    sda_conf['sparsityTarget'] = [0, 0.3, 0]
    sda_conf['sparsityTargetPenalty'] = [0, 0.001, 0]             
    
    sda_conf['anneal_start'] = None # Don't anneal these learning rates
    sda = build_stacked_ae(sda_conf['nvis'], sda_conf['nhid'],
                           sda_conf['act_enc'], sda_conf['act_dec'],
                           corruptor=corruptor,contracting=False, solution=sda_conf['solution'],sparse_penalty=sda_conf['sparse_penalty'],
                           sparsityTarget=sda_conf['sparsityTarget'], sparsityTargetPenalty=sda_conf['sparsityTargetPenalty'])

    # To pretrain it, we'll use a different SGDOptimizer for each layer.
    optimizers = []
    thislayer_input = [minibatch]
    for layer in sda.layers():
      
        cost = MeanSquaredError(layer)(thislayer_input[0],
                                                 layer.reconstruct(thislayer_input[0]))
        opt = SGDOptimizer(layer.params(), sda_conf['base_lr'],
                           sda_conf['anneal_start'])
        optimizers.append((opt, cost))
        # Retrieve a Theano function for training this layer.
        updates = opt.cost_updates(cost)
        thislayer_train_fn = theano.function([minibatch], cost, updates=updates)

        # Train as before.
        for epoch in xrange(2):
            for offset in xrange(0, data.shape[0], batchsize):
                minibatch_err = thislayer_train_fn(
                    data[offset:(offset + batchsize)]
                )
                print "epoch %d, batch %d-%d: %f" % \
                        (epoch, offset, offset + batchsize - 1, minibatch_err)

        # Now, get a symbolic input for the next layer.
        thislayer_input = layer(thislayer_input)
  