import torch
import torch.nn as nn
import torch.optim as optim

model = nn.Linear(10, 1).cuda()
optimizer = optim.Adam(model.parameters())

def train_epoch(loader):
    losses = []
    for batch in loader:
        x, y = batch
        x = x.cuda()
        y = y.cuda()
        pred = model(x)
        loss = nn.functional.mse_loss(pred, y)
        loss.backward()
        optimizer.step()
        losses.append(loss)
    return losses