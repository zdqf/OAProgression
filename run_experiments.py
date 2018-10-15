import sys

import cv2

from torch.optim.lr_scheduler import MultiStepLR

from termcolor import colored


from oaprogression.kvs import GlobalKVS
from oaprogression.training import session
from oaprogression.training import train_utils
from oaprogression.training import dataset
from oaprogression.training import metrics
from oaprogression.training import transforms

cv2.ocl.setUseOpenCL(False)
cv2.setNumThreads(0)

DEBUG = sys.gettrace() is not None

if __name__ == "__main__":
    kvs = GlobalKVS()
    session.init_session()
    dataset.init_metadata()
    session.init_data_processing()
    writers = session.init_folds()

    if DEBUG:
        transforms.debug_augmentations()

    for fold_id in kvs['cv_split_train']:
        kvs.update('cur_fold', fold_id)
        kvs.update('prev_model', None)
        print(colored('====> ', 'blue') + f'Training fold {fold_id}....')

        train_index, val_index = kvs['cv_split_train'][fold_id]
        train_loader, val_loader = session.init_loaders(kvs['metadata'].iloc[train_index],
                                                        kvs['metadata'].iloc[val_index])

        net = train_utils.init_model()
        optimizer = train_utils.init_optimizer([{'params': net.module.classifier_kl.parameters()},
                                                {'params': net.module.classifier_prog.parameters()}])

        scheduler = MultiStepLR(optimizer, milestones=kvs['args'].lr_drop, gamma=0.1)

        for epoch in range(kvs['args'].n_epochs):
            kvs.update('cur_epoch', epoch)
            if epoch == kvs['args'].unfreeze_epoch:
                print(colored('====> ', 'red')+'Unfreezing the layers!')
                new_lr_drop_milestones = list(map(lambda x: x-kvs['args'].unfreeze_epoch, kvs['args'].lr_drop))
                optimizer = train_utils.init_optimizer(net.parameters())
                scheduler = MultiStepLR(optimizer, milestones=new_lr_drop_milestones, gamma=0.1)

            print(colored('====> ', 'red') + 'LR:', scheduler.get_lr())
            train_loss = train_utils.train_epoch(net, optimizer, train_loader)
            val_out = train_utils.validate_epoch(net, val_loader)
            val_loss, val_ids, gt_progression, preds_progression, gt_kl, preds_kl = val_out
            metrics.log_metrics(writers[fold_id], train_loss, val_loss,
                                gt_progression, preds_progression, gt_kl, preds_kl)

            session.save_checkpoint(net, 'auc_prog', 'gt')
            scheduler.step()
